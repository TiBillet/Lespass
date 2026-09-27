"""
Fixtures Playwright pour les tests end-to-end.
/ Playwright fixtures for end-to-end tests.

Prérequis : le serveur Django doit tourner (via Traefik).
/ Prerequisite: Django server must be running (via Traefik).
"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import traceback

import pytest
import requests as http_requests
from playwright.sync_api import sync_playwright


# --- Configuration URL de base / Base URL configuration ---

SUB = os.environ.get("SUB", "lespass")
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
BASE_URL = f"https://{SUB}.{DOMAIN}"

# Chromium résout *.localhost → 127.0.0.1 (RFC 6761), ignorant /etc/hosts.
# On force la résolution vers la gateway Docker (Traefik).
# / Chromium resolves *.localhost → 127.0.0.1 (RFC 6761), ignoring /etc/hosts.
# We force resolution to the Docker gateway (Traefik).
DOCKER_GATEWAY = os.environ.get("DOCKER_GATEWAY", "172.17.0.1")
# La regle `MAP *.domaine` ne couvre que les SOUS-domaines : il faut aussi
# mapper le domaine nu (apex), utilise par les pages ROOT comme /explorer/.
# / The `MAP *.domain` rule only covers SUBdomains: the bare (apex) domain
# must be mapped too — ROOT pages like /explorer/ live there.
CHROMIUM_HOST_RULES = f"MAP *.{DOMAIN} {DOCKER_GATEWAY}, MAP {DOMAIN} {DOCKER_GATEWAY}"

# Détection : on est dans le container si 'docker' n'est pas disponible.
# / Detection: we're inside the container if 'docker' is not available.
INSIDE_CONTAINER = shutil.which("docker") is None

# URL pour les appels HTTP requests (contourne la résolution DNS localhost).
# Depuis le container, on passe par le Docker gateway (Traefik) avec Host header.
# Depuis le host, on utilise l'URL standard.
# / URL for HTTP requests (bypasses localhost DNS resolution).
# From container, go through Docker gateway (Traefik) with Host header.
# From host, use standard URL.
API_BASE_URL = f"https://{DOCKER_GATEWAY}" if INSIDE_CONTAINER else BASE_URL
API_HOST_HEADER = f"{SUB}.{DOMAIN}" if INSIDE_CONTAINER else None


# --- Mode supervision humaine (make e2e-visible) ---
#
# `make e2e-visible` lance, sur l'HOTE, un serveur de navigateur Playwright
# (`playwright run-server`) et donne son adresse par E2E_NAVIGATEUR_DISTANT. Les tests
# tournent toujours dans le conteneur, mais pilotent une fenetre Chromium VISIBLE sur
# l'ecran de l'hote, ralentie de E2E_LENTEUR millisecondes par action. E2E_JOURNAL=1
# ecrit un journal lisible : debut et fin de chaque test, pages, envois, erreurs.
# Sans ces variables (make e2e), rien ne change : Chromium headless dans le conteneur.
# / `make e2e-visible` starts a Playwright browser server on the HOST. Tests still run in
# the container but drive a VISIBLE, slowed-down Chromium window, with a readable log.
NAVIGATEUR_DISTANT = os.environ.get("E2E_NAVIGATEUR_DISTANT", "")
LENTEUR_EN_MS = int(os.environ.get("E2E_LENTEUR") or 0)
JOURNAL_ACTIF = os.environ.get("E2E_JOURNAL") == "1"


# --- Fixtures Playwright / Playwright fixtures ---


@pytest.fixture(scope="session")
def playwright_instance():
    """Démarre Playwright une seule fois par session de tests.
    / Start Playwright once per test session.
    """
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright_instance):
    """Lance Chromium une seule fois par session : headless dans le conteneur, ou
    visible sur l'hote en mode supervision (make e2e-visible).
    / Launch Chromium once per session: headless in the container, or visible on the
    host in supervision mode.
    """
    if NAVIGATEUR_DISTANT:
        # Le navigateur tourne sur l'hote, qui resout lui-meme *.tibillet.localhost :
        # pas de --host-resolver-rules. Les options de lancement passent par l'en-tete
        # que lit `playwright run-server`.
        # / The browser runs on the host, which resolves *.tibillet.localhost itself.
        browser = playwright_instance.chromium.connect(
            NAVIGATEUR_DISTANT,
            slow_mo=LENTEUR_EN_MS,
            headers={"x-playwright-launch-options": json.dumps({"headless": False})},
        )
    else:
        browser = playwright_instance.chromium.launch(
            headless=True,
            args=[f"--host-resolver-rules={CHROMIUM_HOST_RULES}"],
        )
    yield browser
    browser.close()


@pytest.fixture(scope="function")
def page(browser, request):
    """Crée un nouvel onglet (context + page) pour chaque test.
    ignore_https_errors=True car les certificats Traefik sont auto-signés en dev.
    / Create a new tab (context + page) for each test.
    ignore_https_errors=True because Traefik certs are self-signed in dev.

    SUR ECHEC : capture l'ecran et le HTML de la page dans `tests/e2e/artefacts/`.
    Sans ca, un echec E2E ne laisse AUCUNE trace : un `TimeoutError` sur un locator dit
    seulement « je n'ai pas trouve », jamais ce que la page affichait. Un echec qui ne se
    reproduit pas devient alors indiagnosticable, et on en est reduit aux hypotheses.
    / ON FAILURE: dump a screenshot and the page HTML. Without this an E2E failure leaves NO
      trace — a locator TimeoutError only says "not found", never what the page showed.
    """
    context = browser.new_context(
        base_url=BASE_URL,
        ignore_https_errors=True,
    )
    page = context.new_page()
    if JOURNAL_ACTIF:
        _brancher_le_journal(page)

    yield page

    # `rep_call` est pose par le hook `pytest_runtest_makereport` plus bas.
    # On le lit defensivement : si le test a echoue AVANT sa phase d'appel (erreur de
    # fixture), l'attribut n'existe pas.
    # / rep_call is set by the pytest_runtest_makereport hook below. Read it defensively.
    rapport_du_test = getattr(request.node, "rep_call", None)
    if rapport_du_test is not None and rapport_du_test.failed:
        _capturer_la_page_en_echec(page, request.node.nodeid)

    page.close()
    context.close()


# Dossier des artefacts d'echec. Volontairement dans l'arborescence des tests pour qu'on le
# trouve sans le chercher. / Failure artifacts directory, kept next to the tests.
DOSSIER_ARTEFACTS = os.path.join(os.path.dirname(__file__), "artefacts")


# --- Journal de supervision (make e2e-visible) / Supervision log ---

FICHIER_DU_JOURNAL = os.path.join(DOSSIER_ARTEFACTS, "supervision.log")


def _vider_le_journal():
    """Repart d'un journal vide a chaque session. / Start each session with an empty log."""
    os.makedirs(DOSSIER_ARTEFACTS, exist_ok=True)
    with open(FICHIER_DU_JOURNAL, "w", encoding="utf-8"):
        pass


def _journaliser(ligne, saut_de_ligne_a_l_ecran=False):
    """Ecrit une ligne a l'ecran et dans tests/e2e/artefacts/supervision.log.
    `saut_de_ligne_a_l_ecran` : pytest -v vient d'ecrire « PASSED » sans aller a la ligne.
    / Writes a line to the screen and to the supervision log."""
    if saut_de_ligne_a_l_ecran:
        print(flush=True)
    print(ligne, flush=True)
    with open(FICHIER_DU_JOURNAL, "a", encoding="utf-8") as journal:
        journal.write(ligne + "\n")


def _chemin_lisible(adresse):
    """L'adresse sans le domaine, pour un journal lisible. / URL without the domain."""
    from urllib.parse import urlsplit

    morceaux = urlsplit(adresse)
    chemin = morceaux.path + (f"?{morceaux.query}" if morceaux.query else "")
    return chemin[:120]


def _brancher_le_journal(page):
    """
    Journalise ce qui aide un humain a suivre : les pages visitees, les envois (POST,
    requetes HTMX), les reponses en erreur et les erreurs JavaScript. Les chargements de
    fichiers statiques et les GET reussis sont tus : le journal resterait illisible.
    / Logs what helps a human follow along: pages, submissions (POST, HTMX), error
    responses and JavaScript errors. Static files and successful GETs are left out.
    """

    def page_visitee(cadre):
        if cadre == page.main_frame:
            _journaliser(f"  → page     {_chemin_lisible(cadre.url)}")

    def requete_envoyee(requete):
        est_htmx = requete.headers.get("hx-request") == "true"
        if requete.method != "GET" or est_htmx:
            etiquette = " (htmx)" if est_htmx else ""
            _journaliser(f"  → {requete.method:<8} {_chemin_lisible(requete.url)}{etiquette}")

    def reponse_recue(reponse):
        if reponse.status >= 400:
            _journaliser(f"  ✗ {reponse.status}      {_chemin_lisible(reponse.url)}")

    def message_de_console(message):
        if message.type == "error":
            _journaliser(f"  ⚠ console  {message.text[:200]}")

    def erreur_javascript(erreur):
        _journaliser(f"  ⚠ erreur JS  {str(erreur)[:200]}")

    page.on("framenavigated", page_visitee)
    page.on("request", requete_envoyee)
    page.on("response", reponse_recue)
    page.on("console", message_de_console)
    page.on("pageerror", erreur_javascript)


def pytest_sessionstart(session):
    """Repart d'un journal vide, AVANT l'annonce du premier test.
    / Starts from an empty log, BEFORE the first test is announced."""
    if JOURNAL_ACTIF:
        _vider_le_journal()


def pytest_runtest_logstart(nodeid, location):
    """Annonce chaque test dans le journal. / Announces each test in the log."""
    if JOURNAL_ACTIF:
        _journaliser("")
        _journaliser(f"▶ {nodeid}")


def pytest_runtest_logreport(report):
    """Donne l'issue de chaque test dans le journal. / Gives each test's outcome."""
    if not JOURNAL_ACTIF:
        return
    # Le resultat qui compte est celui de l'appel ; un echec en preparation OU en
    # nettoyage (fixture qui verifie apres coup) est aussi dit : pytest le compte en ERROR.
    # / The call outcome matters; a setup or teardown failure is reported too.
    if report.when == "call" or (report.when in ("setup", "teardown") and report.failed):
        if report.passed:
            _journaliser(f"✔ PASSED ({report.duration:.0f} s)", saut_de_ligne_a_l_ecran=True)
        elif report.skipped:
            _journaliser("… SKIPPED", saut_de_ligne_a_l_ecran=True)
        else:
            _journaliser(
                f"✗ FAILED pendant « {report.when} » ({report.duration:.0f} s)",
                saut_de_ligne_a_l_ecran=True,
            )


def _nom_de_fichier_sur(nodeid):
    """Transforme un nodeid pytest en nom de fichier utilisable.
    / Turns a pytest nodeid into a usable file name."""
    caracteres_surs = []
    for caractere in nodeid:
        if caractere.isalnum() or caractere in "-_":
            caracteres_surs.append(caractere)
        else:
            caracteres_surs.append("_")
    # Les nodeid sont longs (chemin + classe + methode) : on garde la fin, la plus parlante.
    # / Node ids are long; keep the tail, which is the telling part.
    return "".join(caracteres_surs)[-120:]


def _capturer_la_page_en_echec(page, nodeid):
    """Ecrit une capture d'ecran et le HTML de la page dans `tests/e2e/artefacts/`.
    / Writes a screenshot and the page HTML into tests/e2e/artefacts/.

    Ne leve jamais : un probleme de capture ne doit pas masquer l'echec du test, qui est
    l'information importante.
    / Never raises: a capture problem must not mask the test failure itself.
    """
    try:
        os.makedirs(DOSSIER_ARTEFACTS, exist_ok=True)
        base = os.path.join(DOSSIER_ARTEFACTS, _nom_de_fichier_sur(nodeid))
        page.screenshot(path=f"{base}.png", full_page=True)
        with open(f"{base}.html", "w", encoding="utf-8") as fichier_html:
            fichier_html.write(page.content())
        print(f"\n[E2E] Echec capture : {base}.png et {base}.html")
    except Exception as erreur_de_capture:
        print(f"\n[E2E] Capture impossible ({erreur_de_capture})")


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """Expose le rapport de chaque phase sur l'item, pour que les fixtures sachent si le
    test a echoue au moment de leur teardown.
    / Exposes each phase report on the item so fixtures know, at teardown, whether the test
      failed. This is the documented pytest recipe for failure artifacts.
    """
    outcome = yield
    rapport = outcome.get_result()
    setattr(item, f"rep_{rapport.when}", rapport)


# --- Fixtures d'authentification / Authentication fixtures ---


@pytest.fixture(scope="session")
def admin_email():
    """Email admin depuis la variable d'environnement ADMIN_EMAIL.
    / Admin email from ADMIN_EMAIL environment variable.
    """
    email = os.environ.get("ADMIN_EMAIL")
    if not email:
        pytest.fail("ADMIN_EMAIL environment variable is not set")
    return email


@pytest.fixture(scope="session")
def e2e_test_token():
    """Token partage avec l'endpoint /api/user/__test_only__/force_login/.
    Lu depuis la variable d'environnement E2E_TEST_TOKEN (voir .env).
    / Shared token with the /api/user/__test_only__/force_login/ endpoint.
    Read from the E2E_TEST_TOKEN environment variable (see .env).
    """
    token = os.environ.get("E2E_TEST_TOKEN")
    if not token:
        pytest.fail(
            "E2E_TEST_TOKEN n'est pas defini dans l'environnement. "
            "Voir la section 'test Playwright' du fichier .env."
        )
    return token


@pytest.fixture(scope="session")
def login_as(e2e_test_token):
    """Factory fixture : retourne une callable (page, email) -> void.

    Injecte un cookie de session authentifie via l'endpoint de test dedie
    (`/api/user/__test_only__/force_login/`). Contourne entierement le flow UI
    (pas de click sur navbar, pas de formulaire, pas de lien TEST MODE).

    Gain : ~100ms au lieu de ~5s, et 6 points de rupture en moins.

    / Factory fixture: returns a callable (page, email) -> void.

    Injects an authenticated session cookie via the dedicated test endpoint.
    Completely bypasses the UI flow (no navbar click, no form, no TEST MODE link).

    Gain: ~100ms instead of ~5s, and 6 fewer failure points.

    DEPENDANCES / DEPENDENCIES :
    - AuthBillet/views_test_only.py (endpoint force_login_for_e2e)
    - .env (E2E_TEST_TOKEN)
    - settings.DEBUG=True (l'endpoint n'est monte que dans ce cas)
    """

    def _login_as(page, email):
        # Etape 1 : appel HTTP vers l'endpoint de force_login.
        # Depuis le container : on passe par le Docker gateway + header Host
        # (Chromium et localhost ne s'entendent pas — cf. conftest haut de fichier).
        # Depuis l'hote : URL standard.
        # / Step 1: HTTP call to the force_login endpoint.
        # From container: via Docker gateway + Host header (Chromium vs localhost).
        # From host: standard URL.
        headers = {"X-Test-Token": e2e_test_token}
        if API_HOST_HEADER:
            headers["Host"] = API_HOST_HEADER

        force_login_url = f"{API_BASE_URL}/api/user/__test_only__/force_login/"
        response = http_requests.post(
            force_login_url,
            headers=headers,
            data={"email": email},
            verify=False,
            timeout=10,
        )
        if not response.ok:
            pytest.fail(
                f"force_login HTTP {response.status_code} pour {email} : "
                f"{response.text[:300]}"
            )

        try:
            payload = response.json()
        except ValueError:
            pytest.fail(f"force_login a renvoye un body non-JSON : {response.text[:300]}")

        session_key = payload.get("sessionid")
        cookie_name = payload.get("session_cookie_name") or "sessionid"
        if not session_key:
            pytest.fail(f"force_login sans session_key : {payload}")

        # Etape 2 : injecte le cookie dans le contexte Playwright.
        # Le domaine doit matcher le subdomain complet du tenant — les cookies
        # de session Django sont per-subdomain.
        # / Step 2: inject cookie in Playwright context.
        # Domain must match the full tenant subdomain — Django session cookies
        # are per-subdomain.
        page.context.add_cookies([{
            "name": cookie_name,
            "value": session_key,
            "domain": f"{SUB}.{DOMAIN}",
            "path": "/",
            "httpOnly": True,
            "secure": False,  # defaults Django : SESSION_COOKIE_SECURE=False
            "sameSite": "Lax",
        }])

    return _login_as


@pytest.fixture(scope="session")
def login_as_admin(login_as, admin_email):
    """Factory fixture : retourne une callable (page) → void.
    Connecte en tant qu'admin.
    / Factory fixture: returns a callable (page) → void.
    Logs in as admin.
    """

    def _login_as_admin(page):
        login_as(page, admin_email)

    return _login_as_admin


@pytest.fixture(scope="session")
def login_as_admin_on_subdomain(e2e_test_token, admin_email):
    """Factory fixture pour les tests cross-tenant : callable (page, subdomain) → void.

    Connecte l'admin sur un tenant precis (identifie par son subdomain, ex:
    "festival") en appelant l'endpoint force_login avec le bon header Host,
    puis en injectant le cookie sur le domaine correspondant.

    Contrairement a `login_as_admin` qui cible toujours le tenant `SUB` (lespass),
    cette fixture permet un login sur n'importe quel tenant existant —
    indispensable pour les tests cross-tenant (ex: federation d'assets).

    / Factory fixture for cross-tenant tests: callable (page, subdomain) → void.
    Unlike `login_as_admin` (always targets `SUB` tenant), this logs the admin
    on any existing tenant — essential for cross-tenant tests (asset federation).

    Usage :
        login_as_admin_on_subdomain(page, "festival")
        page.goto(f"https://festival.{DOMAIN}/admin/fedow_core/asset/")
    """

    def _login_on_subdomain(page, subdomain):
        host_header = f"{subdomain}.{DOMAIN}"

        # Construction URL selon le contexte (container vs hote).
        # Depuis le container, on passe par le Docker gateway + Host header.
        # Depuis l'hote, on utilise l'URL complete du tenant.
        # / URL construction depends on context (container vs host).
        # From container: Docker gateway + Host header. From host: full tenant URL.
        if INSIDE_CONTAINER:
            force_login_url = (
                f"https://{DOCKER_GATEWAY}/api/user/__test_only__/force_login/"
            )
            headers = {
                "X-Test-Token": e2e_test_token,
                "Host": host_header,
            }
        else:
            force_login_url = (
                f"https://{host_header}/api/user/__test_only__/force_login/"
            )
            headers = {"X-Test-Token": e2e_test_token}

        response = http_requests.post(
            force_login_url,
            headers=headers,
            data={"email": admin_email},
            verify=False,
            timeout=10,
        )
        if not response.ok:
            pytest.fail(
                f"force_login (subdomain={subdomain}) HTTP {response.status_code} "
                f"pour {admin_email} : {response.text[:300]}"
            )

        try:
            payload = response.json()
        except ValueError:
            pytest.fail(
                f"force_login (subdomain={subdomain}) body non-JSON : "
                f"{response.text[:300]}"
            )

        session_key = payload.get("sessionid")
        cookie_name = payload.get("session_cookie_name") or "sessionid"
        if not session_key:
            pytest.fail(f"force_login (subdomain={subdomain}) sans session_key : {payload}")

        # Cookie pose sur le subdomain cible (cookies session per-subdomain).
        # / Cookie set on target subdomain (session cookies are per-subdomain).
        page.context.add_cookies([{
            "name": cookie_name,
            "value": session_key,
            "domain": host_header,
            "path": "/",
            "httpOnly": True,
            "secure": False,
            "sameSite": "Lax",
        }])

    return _login_on_subdomain


# --- Fixtures E2E : donnees seedees / E2E fixtures: seeded data ---


@pytest.fixture(scope="session")
def e2e_slugs(django_db_blocker):
    """Renvoie un dict avec les slugs et UUID des fixtures E2E seedees par
    `demo_data_v2` (methode `_seed_e2e_fixtures`).

    Pourquoi cette fixture : Event.save() regenere le slug a chaque appel
    sous la forme `{name}-{datetime}-{pk.hex[:8]}`. Les 8 derniers caracteres
    dependent de l'UUID genere par la DB — donc pas previsibles. On les lit
    depuis la base au demarrage de la session de tests.

    / Returns a dict with slugs and UUIDs of E2E fixtures seeded by
    `demo_data_v2` (`_seed_e2e_fixtures` method).

    Why this fixture: Event.save() regenerates the slug as
    `{name}-{datetime}-{pk.hex[:8]}`. Last 8 chars depend on DB-generated UUID
    — not predictable. We read them from DB at test session start.

    Clefs renvoyees / Returned keys:
    - event_gratuit_slug, event_gratuit_uuid
    - event_payant_slug, event_payant_uuid, event_payant_price_uuid
    - event_gated_slug, event_gated_uuid, event_gated_price_uuid
    - adhesion_uuid, adhesion_price_uuid

    Si une fixture E2E manque (seed pas encore lance), pytest.fail immediat
    avec un message qui explique comment reseed.
    / If a fixture is missing (seed not run yet), immediate pytest.fail with
    a message explaining how to reseed.

    Acces DB : pytest-django bloque les queries par defaut en E2E. On passe
    par `django_db_blocker.unblock()` pour une lecture read-only, sans
    activer le rollback transactionnel (qui casserait les E2E contre un
    serveur reel).
    / DB access: pytest-django blocks queries by default in E2E. We use
    `django_db_blocker.unblock()` for a read-only query, without enabling
    transactional rollback (which would break E2E against a real server).
    """
    from django_tenants.utils import tenant_context
    from Customers.models import Client as TenantClient
    from BaseBillet.models import Event, Product, Price

    def _fail_missing(kind, name):
        pytest.fail(
            f"{kind} E2E '{name}' introuvable dans le tenant lespass. "
            f"Relancer le seed : docker exec lespass_django poetry run "
            f"python manage.py demo_data_v2"
        )

    # Helper : recupere un Event par nom exact ou fail explicite.
    # / Helper: fetch an Event by exact name or fail explicitly.
    def _get_event(name):
        try:
            return Event.objects.get(name=name)
        except Event.DoesNotExist:
            _fail_missing("Event", name)

    # Helper : recupere (Product, Price) par nom exact ou fail explicite.
    # / Helper: fetch (Product, Price) by exact names or fail explicitly.
    def _get_product_and_price(product_name, price_name):
        try:
            product = Product.objects.get(name=product_name)
        except Product.DoesNotExist:
            _fail_missing("Product", product_name)
        try:
            price = product.prices.get(name=price_name)
        except Price.DoesNotExist:
            _fail_missing("Price", f"{product_name} / {price_name}")
        return product, price

    with django_db_blocker.unblock():
        tenant = TenantClient.objects.get(schema_name="lespass")

        with tenant_context(tenant):
            event_gratuit = _get_event("E2E Test — Event gratuit")
            event_payant = _get_event("E2E Test — Event payant")
            event_gated = _get_event("E2E Test — Event gated")

            # Le Price FREERES est auto-cree par le signal post_save
            # (BaseBillet/models.py ligne ~1665). Son nom par defaut est
            # "Tarif gratuit" (_("Free rate") en FR).
            # / The FREERES Price is auto-created by post_save signal.
            # Default name is "Tarif gratuit" ("Free rate" in FR).
            _, price_gratuit = _get_product_and_price(
                "E2E Test — Billet gratuit", "Tarif gratuit"
            )
            _, price_payant = _get_product_and_price(
                "E2E Test — Billet payant", "Plein tarif"
            )
            _, price_gated = _get_product_and_price(
                "E2E Test — Billet gated", "Tarif adherent"
            )
            adhesion, price_adhesion = _get_product_and_price(
                "E2E Test — Adhesion", "Gratuite"
            )

            # Fixtures des E2E du panier (demo_data_v2._seed_e2e_fixtures_du_panier).
            # Si le seed n'a pas été relancé depuis leur ajout, elles manquent : on rend None
            # au lieu d'échouer ici, pour ne pas bloquer les autres E2E. Les tests du panier
            # échouent alors en le disant (tests/e2e/test_panier_flow.py, fixture_du_panier).
            # La récompense exige en plus une monnaie locale du lieu.
            # / Cart E2E fixtures: None if missing, so other E2E tests are not blocked; the
            # cart tests fail explicitly.
            from booking.models import Resource

            def _tarif_ou_none(product_name, price_name):
                return Price.objects.filter(
                    product__name=product_name, name=price_name
                ).select_related("product").first()

            price_adhesion_payante = _tarif_ou_none("E2E Test — Adhesion payante", "Annuelle")
            price_adhesion_recurrente = _tarif_ou_none("E2E Test — Adhesion recurrente", "Mensuelle")
            price_adhesion_recompense = _tarif_ou_none("E2E Test — Adhesion recompense", "Annuelle")
            salle = Resource.objects.filter(name="E2E Test — Salle").first()
            price_salle = None
            if salle is not None and salle.product_id:
                price_salle = salle.product.prices.filter(name="Horaire").first()

            return {
                "adhesion_payante_uuid": (
                    str(price_adhesion_payante.product.uuid) if price_adhesion_payante else None
                ),
                "adhesion_payante_price_uuid": (
                    str(price_adhesion_payante.uuid) if price_adhesion_payante else None
                ),
                "adhesion_recurrente_uuid": (
                    str(price_adhesion_recurrente.product.uuid) if price_adhesion_recurrente else None
                ),
                "adhesion_recurrente_price_uuid": (
                    str(price_adhesion_recurrente.uuid) if price_adhesion_recurrente else None
                ),
                "adhesion_recompense_uuid": (
                    str(price_adhesion_recompense.product.uuid) if price_adhesion_recompense else None
                ),
                "adhesion_recompense_price_uuid": (
                    str(price_adhesion_recompense.uuid) if price_adhesion_recompense else None
                ),
                "salle_resource_pk": str(salle.pk) if price_salle else None,
                "salle_price_uuid": str(price_salle.uuid) if price_salle else None,
                "event_gratuit_slug": event_gratuit.slug,
                "event_gratuit_uuid": str(event_gratuit.uuid),
                "event_gratuit_price_uuid": str(price_gratuit.uuid),
                "event_payant_slug": event_payant.slug,
                "event_payant_uuid": str(event_payant.uuid),
                "event_payant_price_uuid": str(price_payant.uuid),
                "event_gated_slug": event_gated.slug,
                "event_gated_uuid": str(event_gated.uuid),
                "event_gated_price_uuid": str(price_gated.uuid),
                "adhesion_uuid": str(adhesion.uuid),
                "adhesion_price_uuid": str(price_adhesion.uuid),
            }


# --- Fixtures API et shell / API and shell fixtures ---


def _run_command(cmd_docker, cmd_local, timeout=30):
    """Exécute cmd_docker (hôte) ou cmd_local (container) selon le contexte.
    / Run cmd_docker (host) or cmd_local (container) depending on context.
    """
    cmd = cmd_local if INSIDE_CONTAINER else cmd_docker
    env = {**os.environ, "TEST": "1", "PYTHONPATH": "/DjangoFiles"} if INSIDE_CONTAINER else None
    cwd = "/DjangoFiles" if INSIDE_CONTAINER else None
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        env=env, cwd=cwd,
    )


@pytest.fixture(scope="session")
def api_key():
    """Récupère la clé API : celle que scripts/lancer_tests.sh passe dans API_KEY,
    sinon via manage.py test_api_key (lancement de pytest à la main).
    / Fetches the API key: the one scripts/lancer_tests.sh passes in API_KEY,
    otherwise through manage.py test_api_key (pytest launched by hand).
    """
    cle_du_script = os.environ.get("API_KEY", "").strip()
    if cle_du_script:
        return cle_du_script
    result = _run_command(
        cmd_docker=[
            "docker", "exec", "-e", "TEST=1",
            "lespass_django", "poetry", "run", "python",
            "manage.py", "test_api_key",
        ],
        cmd_local=["python", "manage.py", "test_api_key"],
    )
    if result.returncode != 0:
        pytest.fail(f"test_api_key failed: {result.stderr}")
    key = result.stdout.strip()
    if not key:
        pytest.fail("test_api_key returned an empty key")
    return key


@pytest.fixture(scope="session")
def django_shell(django_db_blocker):
    """Factory : exécute du Python DANS le processus pytest, dans le contexte d'un lieu.
    Renvoie ce que le code a imprimé (print), et lève RuntimeError si le code lève.
    / Factory: runs Python IN the pytest process, inside a tenant's context.
    Returns what the code printed, raises RuntimeError if the code raises.

    Usage : result = django_shell("from laboutik.models import PointDeVente; print(PointDeVente.objects.count())")
    Usage : result = django_shell("...", schema="festival")

    Avant, chaque appel lançait `manage.py tenant_command shell` : environ 4,7 s de
    démarrage de Django par appel. Ici, le code tourne tout de suite. Les écritures
    sont validées aussitôt (autocommit), donc le serveur les voit.
    / Previously each call spawned `manage.py tenant_command shell` (~4.7 s of Django
    boot). Writes are committed at once (autocommit), so the server sees them.
    """
    from django.test.utils import override_settings
    from django_tenants.utils import tenant_context
    from Customers.models import Client as TenantClient

    # pytest-django force DEBUG=False dans ce processus. Le serveur, lui, tourne avec
    # le DEBUG du .env. Sans ce réglage, FedowAPI passe en verify=True (erreur SSL sur
    # le certificat de dev) et reset_carte refuse sans rien dire.
    # / pytest-django forces DEBUG=False here; mirror the server's DEBUG from .env,
    # otherwise FedowAPI verifies the dev certificate (SSLError) and reset_carte refuses.
    debug_du_serveur = os.environ.get("DEBUG") == "1"

    def _run(python_code, schema="lespass"):
        sortie = io.StringIO()
        try:
            with django_db_blocker.unblock(), override_settings(DEBUG=debug_du_serveur):
                # Le vrai lieu, pas schema_context : celui-ci pose un faux lieu
                # (FakeTenant) sans uuid ni name, que certains codes lisent.
                # / The real tenant: schema_context sets a FakeTenant without uuid/name.
                tenant = TenantClient.objects.get(schema_name=schema)
                with tenant_context(tenant), contextlib.redirect_stdout(sortie):
                    exec(python_code, {"__name__": "__main__"})
        except Exception as erreur:
            raise RuntimeError(
                f"django_shell failed: {erreur!r}\n{traceback.format_exc()}\n"
                f"stdout: {sortie.getvalue()[-2000:]}"
            ) from erreur
        return sortie.getvalue().strip()

    return _run


# --- Fixture comptable / Accounting fixture ---


@pytest.fixture(scope="session")
def instant_serveur(django_shell):
    """Factory : l'heure COURANTE telle que la base la voit, en ISO 8601.

    / Factory: the CURRENT time as the database sees it, ISO 8601.

    Sert a poser la borne de depart d'une fenetre comptable juste avant l'action
    qu'on veut mesurer. L'heure doit venir du serveur, pas du processus de test :
    les deux peuvent etre sur des fuseaux differents, et un decalage de quelques
    heures ferait lire une fenetre vide sans qu'aucune assertion ne le signale.
    / Take the time from the server, not the test process: a timezone gap would
    silently read an empty window.
    """

    def _maintenant():
        sortie = django_shell(
            "from django.utils import timezone\n"
            "print('INSTANT=' + timezone.localtime().isoformat())"
        )
        for ligne in sortie.splitlines():
            if ligne.startswith("INSTANT="):
                return ligne[len("INSTANT=") :]
        pytest.fail(f"Heure serveur illisible. Sortie : {sortie[-300:]}")

    return _maintenant


@pytest.fixture(scope="session")
def rapports_comptables(django_shell):
    """Factory : lit les DEUX rapports comptables depuis un instant donne.

    / Factory: reads BOTH accounting reports since a given instant.

    POURQUOI DEUX RAPPORTS / WHY TWO REPORTS
    ------------------------------------------
    Lespass en tient deux, avec des perimetres complementaires, et une vente
    n'apparait JAMAIS dans les deux :

    - **caisse** — `laboutik.reports.RapportComptableService`, ce que le caissier
      cloture en fin de service (ticket X, ticket Z). Ne lit que les origines de
      `ORIGINES_ENCAISSEES_PAR_LE_LIEU` : `LABOUTIK` et `TIREUSE`.
    - **en_ligne** — `comptabilite.services.RapportComptableService`, la cloture
      comptable des ventes a distance. Prend tout SAUF `LABOUTIK`.

    Une vente correctement enregistree peut donc etre **invisible des deux** si
    elle porte une origine mal choisie. C'est arrive aux remboursements de carte
    (`ADMIN` au lieu de `LABOUTIK`) et aux ventes de tireuse. Verifier la seule
    `LigneArticle` ne suffit pas : elle existe dans tous ces cas.

    / A correctly recorded sale can be invisible to BOTH reports if it carries the
    wrong origin. Checking the LigneArticle alone never catches this.

    USAGE — poser la borne AVANT l'action, lire APRES :

        depuis = instant_serveur()
        # ... l'action qui encaisse ...
        comptes = rapports_comptables(depuis)
        assert comptes["caisse"]["especes"] == 500      # EXACT, pas un ecart

    POURQUOI UNE BORNE FIXE, ET PAS DEUX MESURES / WHY A FIXED LOWER BOUND
    -----------------------------------------------------------------------
    La tentation est de mesurer avant, mesurer apres, et soustraire. Sur une
    fenetre **glissante** (« les 6 dernieres heures »), c'est faux : entre les
    deux mesures, la borne basse avance elle aussi, et de vieilles lignes sortent
    de la fenetre par la gauche pendant que la nouvelle vente y entre par la
    droite. Sur une base de developpement bien remplie, les deux mouvements se
    compensent — l'ecart mesure vaut alors zero alors que la vente est
    parfaitement comptabilisee.

    En ancrant la borne basse a un instant fixe, la fenetre ne fait que
    s'agrandir : elle ne contient QUE ce que le test vient de produire. Les
    montants deviennent **exacts** au lieu d'etre des ecarts, ce qui est aussi
    plus severe — un total juste ne peut plus se confondre avec un total qui a
    seulement augmente.
    / A sliding window makes deltas wrong: old lines leave on the left while the
    new sale enters on the right, and on a well-filled dev DB the two cancel out.
    A fixed lower bound only ever grows, so the window contains ONLY what the test
    just produced — and the amounts become exact rather than relative.

    :param depuis: borne basse, chaine ISO 8601 rendue par `instant_serveur()`.
    :param nom_du_point_de_vente: PV dont on lit le rapport de caisse. `None`
        (defaut) = tous points de vente confondus. Sans effet sur le perimetre
        des lignes : la cloture est globale au tenant (PIEGES 9.64).
    :return: dict {"caisse": {...}, "en_ligne": {...}}
    """

    def _lire(depuis, nom_du_point_de_vente=None):
        filtre_pv = (
            f"PointDeVente.objects.filter(name='{nom_du_point_de_vente}').first()"
            if nom_du_point_de_vente
            else "None"
        )
        sortie = django_shell(
            "import json\n"
            "from django.utils.dateparse import parse_datetime\n"
            "from django.utils import timezone\n"
            "from laboutik.models import PointDeVente\n"
            "from laboutik.reports import RapportComptableService as RapportCaisse\n"
            "from comptabilite.services import RapportComptableService as RapportEnLigne\n"
            "fin = timezone.localtime()\n"
            f"debut = parse_datetime('{depuis}')\n"
            f"pv = {filtre_pv}\n"
            "caisse = RapportCaisse(pv, debut, fin)\n"
            "moyens = caisse.calculer_totaux_par_moyen()\n"
            "recharges = caisse.calculer_recharges()\n"
            "adhesions = caisse.calculer_adhesions()\n"
            "en_ligne = RapportEnLigne(debut, fin)\n"
            "moyens_en_ligne = en_ligne.calculer_totaux_par_moyen()\n"
            "print('RAPPORTS_JSON=' + json.dumps({\n"
            "    'caisse': {\n"
            "        'especes': int(moyens.get('especes') or 0),\n"
            "        'carte_bancaire': int(moyens.get('carte_bancaire') or 0),\n"
            "        'total_recharges': int(recharges.get('total') or 0),\n"
            "        'total_adhesions': int(adhesions.get('total') or 0),\n"
            "        'solde_caisse': int(caisse.calculer_solde_caisse().get('solde') or 0),\n"
            "    },\n"
            "    'en_ligne': {\n"
            "        cle: int(valeur)\n"
            "        for cle, valeur in (moyens_en_ligne or {}).items()\n"
            "        if isinstance(valeur, (int, float))\n"
            "    },\n"
            "}))"
        )
        for ligne in sortie.splitlines():
            if ligne.startswith("RAPPORTS_JSON="):
                return json.loads(ligne[len("RAPPORTS_JSON=") :])
        pytest.fail(
            "Lecture des rapports comptables impossible — le shell Django n'a "
            f"rien imprime derriere RAPPORTS_JSON=. Sortie : {sortie[-500:]}"
        )

    return _lire


@pytest.fixture(scope="session")
def rapports_qui_voient_la_ligne(django_shell):
    """Factory : dans LEQUEL des deux rapports comptables une ligne precise entre.

    / Factory: which of the two accounting reports a given line falls into.

    POURQUOI CE HELPER PLUTOT QU'UN TOTAL / WHY THIS RATHER THAN A TOTAL
    ---------------------------------------------------------------------
    Asserter un montant exact sur le rapport **en ligne** n'est pas fiable en
    E2E : ses lignes arrivent par des webhooks Stripe, donc de facon
    **asynchrone**. Le webhook d'un test precedent peut tomber pendant le test
    suivant, et gonfler son total sans aucun rapport avec ce qu'il mesure. C'est
    arrive : un renouvellement attendu a 100 relevait 200.

    Le rapport de **caisse** n'a pas ce probleme (aucune source asynchrone), et
    ses montants peuvent, eux, etre asserted au centime.

    Ce helper repond a la seule question qui soit a la fois deterministe et
    metier : **cette vente-la est-elle vue par un rapport, et lequel ?** Une
    vente qui n'entre dans aucun des deux n'existe pour aucun comptable ; une
    vente qui entre dans les deux est comptee deux fois.

    / Asserting exact totals on the ONLINE report is unreliable: its lines arrive
    via asynchronous Stripe webhooks, so a previous test's webhook can land during
    the next one (observed: 200 where 100 was expected). The REGISTER report has
    no async source and can be asserted to the cent. This helper answers the only
    question that is both deterministic and meaningful: is THIS sale seen by a
    report, and which one?

    :param uuid_de_la_ligne: uuid de la `LigneArticle` a situer.
    :param depuis: borne basse ISO 8601, rendue par `instant_serveur()`.
    :return: dict {"caisse": bool, "en_ligne": bool}
    """

    def _situer(uuid_de_la_ligne, depuis):
        sortie = django_shell(
            "import json\n"
            "from django.utils.dateparse import parse_datetime\n"
            "from django.utils import timezone\n"
            "from laboutik.reports import RapportComptableService as RapportCaisse\n"
            "from comptabilite.services import RapportComptableService as RapportEnLigne\n"
            "fin = timezone.localtime()\n"
            f"debut = parse_datetime('{depuis}')\n"
            f"uuid_vise = '{uuid_de_la_ligne}'\n"
            "caisse = RapportCaisse(None, debut, fin)\n"
            "en_ligne = RapportEnLigne(debut, fin)\n"
            "print('SITUATION_JSON=' + json.dumps({\n"
            "    'caisse': caisse.lignes.filter(uuid=uuid_vise).exists(),\n"
            "    'en_ligne': en_ligne.queryset.filter(uuid=uuid_vise).exists(),\n"
            "}))"
        )
        for ligne in sortie.splitlines():
            if ligne.startswith("SITUATION_JSON="):
                return json.loads(ligne[len("SITUATION_JSON=") :])
        pytest.fail(
            "Impossible de situer la ligne dans les rapports — le shell Django "
            f"n'a rien imprime derriere SITUATION_JSON=. Sortie : {sortie[-500:]}"
        )

    return _situer


@pytest.fixture(scope="session")
def create_event(api_key):
    """Factory : crée un événement via l'API v2.
    / Factory: creates an event via the API v2.

    Retourne dict {ok, slug, uuid, data}.
    """

    def _slugify(value):
        slug = value.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")

    def _slug_from_url(url):
        if not url:
            return None
        parts = [p for p in url.split("/") if p]
        try:
            idx = parts.index("event")
            return parts[idx + 1]
        except (ValueError, IndexError):
            return None

    def _create(name, start_date, max_per_user=None,
                options_radio=None, options_checkbox=None):
        additional_property = []
        if options_radio:
            additional_property.append({
                "@type": "PropertyValue",
                "name": "optionsRadio",
                "value": options_radio,
            })
        if options_checkbox:
            additional_property.append({
                "@type": "PropertyValue",
                "name": "optionsCheckbox",
                "value": options_checkbox,
            })

        payload = {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": name,
            "startDate": start_date,
        }
        if max_per_user is not None:
            payload["offers"] = {"eligibleQuantity": {"maxValue": max_per_user}}
        if additional_property:
            payload["additionalProperty"] = additional_property

        headers = {
            "Authorization": f"Api-Key {api_key}",
            "Content-Type": "application/json",
        }
        if API_HOST_HEADER:
            headers["Host"] = API_HOST_HEADER

        resp = http_requests.post(
            f"{API_BASE_URL}/api/v2/events/",
            headers=headers,
            json=payload,
            verify=False,
        )
        data = None
        try:
            data = resp.json()
        except Exception:
            pass

        slug = (
            _slug_from_url(data.get("url") if data else None)
            or _slugify(name)
        )
        return {
            "ok": resp.ok,
            "status": resp.status_code,
            "slug": slug,
            "uuid": data.get("identifier") if data else None,
            "data": data,
        }

    return _create


@pytest.fixture(scope="session")
def create_product(api_key):
    """Factory : crée un produit via l'API v2.
    / Factory: creates a product via the API v2.

    Retourne dict {ok, uuid, offers, data}.
    """

    def _create(name, category="Ticket booking", description="",
                event_uuid=None, offers=None, form_fields=None):
        additional_property = []
        if form_fields:
            additional_property.append({
                "@type": "PropertyValue",
                "name": "formFields",
                "value": form_fields,
            })

        offers_payload = []
        for offer in (offers or []):
            offer_additional = []
            if offer.get("recurringPayment") is not None:
                offer_additional.append({
                    "@type": "PropertyValue",
                    "name": "recurringPayment",
                    "value": offer["recurringPayment"],
                })
            if offer.get("subscriptionType"):
                offer_additional.append({
                    "@type": "PropertyValue",
                    "name": "subscriptionType",
                    "value": offer["subscriptionType"],
                })
            if offer.get("manualValidation") is not None:
                offer_additional.append({
                    "@type": "PropertyValue",
                    "name": "manualValidation",
                    "value": offer["manualValidation"],
                })

            offers_payload.append({
                "@type": "Offer",
                "name": offer["name"],
                "price": offer["price"],
                "priceCurrency": "EUR",
                "freePrice": offer.get("freePrice"),
                "stock": offer.get("stock"),
                "maxPerUser": offer.get("maxPerUser"),
                "additionalProperty": offer_additional or None,
            })

        payload = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": name,
            "description": description,
            "category": category,
        }
        if event_uuid:
            payload["isRelatedTo"] = {
                "@type": "Event",
                "identifier": event_uuid,
            }
        if offers_payload:
            payload["offers"] = offers_payload
        if additional_property:
            payload["additionalProperty"] = additional_property

        headers = {
            "Authorization": f"Api-Key {api_key}",
            "Content-Type": "application/json",
        }
        if API_HOST_HEADER:
            headers["Host"] = API_HOST_HEADER

        resp = http_requests.post(
            f"{API_BASE_URL}/api/v2/products/",
            headers=headers,
            json=payload,
            verify=False,
        )
        data = None
        try:
            data = resp.json()
        except Exception:
            pass

        return {
            "ok": resp.ok,
            "status": resp.status_code,
            "uuid": data.get("identifier") if data else None,
            "offers": data.get("offers") if data else None,
            "data": data,
        }

    return _create


@pytest.fixture(scope="session")
def setup_test_data():
    """Factory : exécute le script setup_test_data.py dans le container.
    / Factory: runs setup_test_data.py script inside the container.

    Usage : result = setup_test_data("create_promotional_code", product="...", code_name="...")
    """

    def _run(action, **kwargs):
        args = ["--action", action]
        for key, value in kwargs.items():
            cli_key = key.replace("_", "-")
            args.extend([f"--{cli_key}", str(value)])

        result = _run_command(
            cmd_docker=[
                "docker", "exec", "-w", "/DjangoFiles",
                "-e", "PYTHONPATH=/DjangoFiles",
                "lespass_django", "poetry", "run", "python",
                "tests/scripts/setup_test_data.py",
            ] + args,
            cmd_local=[
                "python", "tests/scripts/setup_test_data.py",
            ] + args,
        )
        if result.returncode != 0:
            return {"status": "error", "message": result.stderr}
        try:
            return json.loads(result.stdout)
        except Exception:
            return {"status": "error", "message": result.stdout}

    return _run


@pytest.fixture(scope="session")
def ensure_pos_data():
    """S'assure que les données POS de test existent (catégories, produits, PV).
    Exécuté une seule fois par session de test.
    / Ensures test POS data exists (categories, products, POS).
    Run once per test session.
    """
    result = _run_command(
        cmd_docker=[
            "docker", "exec", "-e", "TEST=1",
            "lespass_django", "poetry", "run", "python",
            "manage.py", "create_test_pos_data",
        ],
        cmd_local=["python", "manage.py", "create_test_pos_data"],
        timeout=60,
    )
    if result.returncode != 0:
        pytest.fail(
            f"create_test_pos_data a échoué (rc={result.returncode}): "
            f"{result.stderr or result.stdout}"
        )


@pytest.fixture(scope="function")
def pos_page(browser, login_as_admin, django_shell, ensure_pos_data):
    """Factory : ouvre la caisse POS pour un point de vente donné.
    / Factory: opens the POS for a given point of sale.

    Usage : pos = pos_page(page, "Bar")
    Usage : pos = pos_page(page, "Adhesions")
    Retourne la page Playwright prête sur la caisse.
    """
    demo_tag_id = os.environ.get("DEMO_TAGID_CM", "A49E8E2A")

    def _open_pos(page, pv_name_filter="Bar", comportement=None):
        # Récupérer l'UUID du PDV / Get POS UUID
        if comportement:
            query = f"PointDeVente.objects.filter(comportement='{comportement}').first()"
            label = f"comportement={comportement}"
        else:
            query = f"PointDeVente.objects.filter(name='{pv_name_filter}').first()"
            label = f'name={pv_name_filter}'
        result = django_shell(
            f"from laboutik.models import PointDeVente; "
            f"pv = {query}; "
            f"print(f'uuid={{pv.uuid}}') if pv else print('NOT_FOUND')"
        )
        uuid_match = re.search(r"uuid=(.+)", result)
        if not uuid_match:
            pytest.fail(
                f'PDV ({label}) introuvable. '
                f"Lancer create_test_pos_data d'abord. Résultat: {result}"
            )
        pv_uuid = uuid_match.group(1).strip()

        # Login admin / Admin login
        login_as_admin(page)

        # Naviguer vers la caisse / Navigate to POS
        page.goto(
            f"/laboutik/caisse/point_de_vente/"
            f"?uuid_pv={pv_uuid}&tag_id_cm={demo_tag_id}"
        )
        page.wait_for_load_state("networkidle")
        page.locator("#products").wait_for(state="visible", timeout=10_000)
        return page

    return _open_pos


# --- Fixture Stripe E2E / Stripe E2E fixture ---


@pytest.fixture(scope="session")
def fill_stripe_card():
    """Factory : remplit le formulaire Stripe checkout (vrai checkout.stripe.com).
    / Factory: fills the Stripe checkout form (real checkout.stripe.com).

    Converti depuis tests/playwright/tests/utils/stripe.ts.
    Carte test : 4242 4242 4242 4242, 12/42, 424, Douglas Adams.
    """

    def _fill(page, email):
        # Remplir l'email si visible / Fill email if visible
        email_input = page.locator('input#email, input[name="email"]').first
        if email_input.is_visible(timeout=3_000):
            email_input.fill(email)

        # Sélection du moyen de paiement "Carte".
        # Quand plusieurs moyens sont actifs (ex: Carte + Prélèvement SEPA), Stripe
        # Checkout affiche un accordéon : les champs carte ne sont révélés qu'après
        # avoir déplié l'item "Carte". Le bouton porte un data-testid stable
        # (indépendant de la langue). Sa zone de clic chevauche le radio (qui
        # intercepte les events), d'où le clic forcé. Si la carte est le seul moyen,
        # ce bouton n'existe pas : on ne fait rien (no-op).
        # / Pick the "Card" payment method. With several methods (e.g. Card + SEPA),
        # Stripe Checkout shows an accordion; the card fields only appear after
        # expanding the "Card" item. The button has a stable data-testid; its click
        # area overlaps the radio (which intercepts events), hence the forced click.
        # No-op when card is the only method (button absent).
        # Attendre que le formulaire de paiement Stripe soit monté (SPA React).
        # Deux cas possibles :
        #  - SEPA activé : un accordéon de moyens de paiement (Carte + SEPA) ;
        #  - SEPA désactivé : les champs carte directement (carte seule).
        # On attend donc l'un OU l'autre, pour ne pas tester trop tôt (le test
        # arrive en "domcontentloaded", avant le rendu React).
        # / Wait for Stripe's payment form to mount. Two cases: a methods accordion
        # (Card + SEPA) or the card field directly (card only). Wait for either.
        try:
            page.locator(
                '[data-testid="card-accordion-item-button"], input#cardNumber'
            ).first.wait_for(state="visible", timeout=20_000)
        except Exception:
            pass

        # Si l'accordéon "Carte" est présent (plusieurs moyens actifs), il faut le
        # déplier pour révéler les champs carte. S'il est absent (carte seule), on
        # ne fait rien : les champs sont déjà affichés.
        # / If the "Card" accordion is present (several methods), expand it to
        # reveal the card fields. If absent (card only), do nothing.
        bouton_carte = page.locator('[data-testid="card-accordion-item-button"]').first
        try:
            if bouton_carte.count() > 0:
                # On envoie directement l'événement DOM "click" : la zone de clic
                # de Stripe chevauche le radio (interception) et déjoue un clic
                # Playwright classique, alors qu'un dispatch_event déplie bien
                # l'accordéon. / Dispatch the DOM click event directly: Stripe's
                # overlapping click area defeats a regular Playwright click, while
                # dispatch_event reliably expands the accordion.
                bouton_carte.dispatch_event('click')
                # Attendre l'apparition des champs carte (sinon on continue).
                # / Wait for the card fields to appear (otherwise just continue).
                try:
                    page.locator('input#cardNumber').first.wait_for(
                        state="visible", timeout=5_000
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # Stratégie 1 : sélecteurs par rôle (Stripe Checkout récent)
        # / Strategy 1: role-based selectors (recent Stripe Checkout)
        card_number = page.get_by_role("textbox", name=re.compile(r"card number", re.I)).first
        try:
            card_number.wait_for(state="visible", timeout=5_000)
            card_number.fill("4242424242424242")
            page.get_by_role("textbox", name=re.compile(r"expiration", re.I)).first.fill("12/42")
            page.get_by_role("textbox", name=re.compile(r"cvc", re.I)).first.fill("424")
            cardholder = page.get_by_role("textbox", name=re.compile(r"cardholder name", re.I)).first
            if cardholder.is_visible(timeout=2_000):
                cardholder.fill("Douglas Adams")
            return
        except Exception:
            pass

        # Stratégie 2 : sélecteurs par ID (Stripe Checkout classique)
        # / Strategy 2: ID-based selectors (classic Stripe Checkout)
        card_by_id = page.locator("input#cardNumber").first
        if card_by_id.is_visible(timeout=3_000):
            card_by_id.fill("4242424242424242")
            page.locator("input#cardExpiry").fill("12/42")
            page.locator("input#cardCvc").fill("424")
            billing_name = page.locator("input#billingName").first
            if billing_name.is_visible(timeout=2_000):
                billing_name.fill("Douglas Adams")
            return

        # Stratégie 3 : sélecteurs par attribut (fallback)
        # / Strategy 3: attribute-based selectors (fallback)
        fallback = page.locator('input[name="cardnumber"], input[placeholder*="1234"]').first
        if fallback.is_visible(timeout=3_000):
            fallback.fill("4242424242424242")
            exp = page.locator('input[name="exp-date"], input[placeholder*="MM"]').first
            if exp.is_visible():
                exp.fill("12/42")
            cvc = page.locator('input[name="cvc"], input[placeholder*="CVC"]').first
            if cvc.is_visible():
                cvc.fill("424")
            return

        # Stratégie 4 : iframes (Stripe Elements embedded)
        # Stripe peut utiliser des iframes pour les champs de carte.
        # Converti depuis tests/playwright/tests/utils/stripe.ts (stratégie 4).
        # / Strategy 4: iframes (Stripe Elements embedded)
        # Stripe may use iframes for card fields.
        # Converted from tests/playwright/tests/utils/stripe.ts (strategy 4).
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            number_input = frame.locator(
                'input[name="cardnumber"], input[placeholder*="1234"]'
            ).first
            if number_input.count() > 0:
                number_input.fill("4242424242424242")
                frame.locator('input[name="exp-date"], input[placeholder*="MM"]').first.fill("12/42")
                frame.locator('input[name="cvc"], input[placeholder*="CVC"]').first.fill("424")
                return

        # Aucune des strategies n'a trouve de champ de carte : Stripe a change son
        # formulaire. On echoue ICI, plutot que de laisser le test cliquer « Payer »
        # dans le vide pendant des minutes et accuser le mauvais endroit.
        # / No strategy found a card field: fail HERE rather than click "Pay" in vain.
        pytest.fail(f"Aucun champ de carte bancaire trouve sur la page Stripe ({page.url}).")

    return _fill


@pytest.fixture(scope="session")
def soumettre_paiement_stripe():
    """Factory : soumet le formulaire Stripe Checkout, et insiste jusqu'à ce que ça parte.

    / Factory: submits the Stripe Checkout form, insisting until it actually fires.

    POURQUOI CETTE FIXTURE / WHY THIS FIXTURE
    -------------------------------------------
    Sur ce checkout, un `click()` Playwright donne bien le **focus** au bouton
    « Pay » — le contour bleu est visible sur une capture — mais ne déclenche
    **aucune requête réseau**. Le paiement ne part pas, rien ne s'affiche à
    l'écran, aucune erreur de console : le test attend jusqu'à expiration et
    échoue sur un timeout de navigation, ce qui envoie le diagnostic vers le
    mauvais endroit (l'URL de retour, le webhook, le prestataire).

    / A plain click() focuses the "Pay" button but fires NO network request. The
    payment never starts, nothing is displayed, no console error: the test waits
    until timeout and fails on a navigation error, which points the diagnosis at
    the wrong place.

    La parade : réessayer en alternant `click()` et `dispatch_event('click')`
    jusqu'à ce que la page quitte `checkout.stripe.com`. Même parade que pour
    l'accordéon des moyens de paiement dans `fill_stripe_card` ci-dessus.

    Un `dispatch_event` **seul** ne suffit pas : le premier `click()` et
    l'attente qui le suit sont nécessaires, le temps que le formulaire React
    finisse de se valider.

    Mesuré sur `test_recharge_federee_par_carte_bancaire` : le fichier passe de
    ~2 min (quatre attentes vaines de 45 s) à ~47 s. Voir `PIEGES.md` 12.14.

    ATTENTION AU SÉLECTEUR PAR DÉFAUT : son repli `button[type="submit"]` est très large.
    Il n'est acceptable QUE parce que cette fonction refuse d'agir dès que la page a quitté
    `checkout.stripe.com` — sans cette garde, il attrape le premier bouton de formulaire de
    la page d'arrivée (souvent invisible) et fait échouer un paiement pourtant réussi.
    / MIND THE DEFAULT SELECTOR: its `button[type="submit"]` fallback is very broad. It is
      only acceptable because this function refuses to act once the page has left the
      checkout — otherwise it grabs the destination page's first form button.

    :param page: la page Playwright, arrivée sur checkout.stripe.com
    :param selecteur: le bouton à actionner. Par défaut celui du checkout hébergé.
    :param tentatives: nombre de couples (click, dispatch) avant d'abandonner.
    :return: True si la page a quitté Stripe, False sinon — l'appelant décide
        quoi en faire (la plupart enchaînent sur un `wait_for_url` qui portera
        le message d'erreur métier).
    """

    def _est_encore_sur_stripe(page):
        """La page est-elle toujours sur le checkout ? / Still on the checkout page?"""
        return "checkout.stripe.com" in page.url

    def _attendre_la_sortie_du_checkout(page, delai_ms):
        """Attend que la page quitte Stripe. Rend True si elle l'a quittee.
        / Waits for the page to leave Stripe. Returns True if it did.

        On attend un EVENEMENT (le changement d'URL), pas une duree fixe. Le retour de
        paiement est une chaine de redirections — Stripe, puis le retour construit par
        Fedow, puis `return_refill_wallet`, puis `/my_account/`. Une pause fixe trop courte
        conclut « toujours sur Stripe » alors que la navigation est en vol.
        / Wait for an EVENT (the URL change), not a fixed delay: the payment return is a
          redirect chain, and a too-short fixed pause concludes "still on Stripe" while the
          navigation is in flight.
        """
        try:
            page.wait_for_url(
                lambda url: "checkout.stripe.com" not in url, timeout=delai_ms
            )
            return True
        except Exception:
            return False

    def _soumettre(
        page,
        selecteur='[data-testid="hosted-payment-submit-button"], button[type="submit"]',
        tentatives=6,
    ):
        # GARDE D'ENTREE : si la page a deja quitte le checkout, il n'y a rien a soumettre.
        # Sans elle, le selecteur est evalue sur la page d'ARRIVEE, ou son repli
        # `button[type="submit"]` — tres large — attrape n'importe quel bouton de
        # formulaire, souvent invisible. On attend alors 30 s sur un bouton sans rapport,
        # et l'echec accuse le paiement alors qu'il a reussi.
        # / ENTRY GUARD: if the page already left the checkout there is nothing to submit.
        #   Without it the selector is evaluated on the DESTINATION page, where the broad
        #   `button[type="submit"]` fallback grabs an unrelated, often invisible button.
        if not _est_encore_sur_stripe(page):
            return True

        bouton = page.locator(selecteur).first
        bouton.wait_for(state="visible", timeout=30_000)

        for _tentative in range(tentatives):
            # Meme garde AVANT chaque action : le clic precedent a pu partir et la
            # navigation se terminer entre-temps. Cliquer maintenant viserait la page
            # d'arrivee.
            # / Same guard BEFORE each action: the previous click may have fired and the
            #   navigation completed since. Clicking now would target the destination page.
            if not _est_encore_sur_stripe(page):
                return True

            bouton.click()
            if _attendre_la_sortie_du_checkout(page, 8_000):
                return True

            if not _est_encore_sur_stripe(page):
                return True

            bouton.dispatch_event("click")
            if _attendre_la_sortie_du_checkout(page, 8_000):
                return True
        # Le paiement n'est jamais parti : on echoue ICI, avec la vraie cause, plutot
        # que de laisser le test attendre un retour qui ne viendra pas.
        # / The payment never left: fail HERE with the real cause.
        pytest.fail(
            f"Le paiement Stripe ne part pas : {tentatives} tentatives de clic sur "
            f"« {selecteur} » sans quitter checkout.stripe.com ({page.url})."
        )

    return _soumettre


# ---------------------------------------------------------------------------
# Tests qui exigent `stripe listen` (Stripe reel)
# ---------------------------------------------------------------------------
#
# Certains parcours ne s'achevent que lorsque Stripe rappelle le webhook de
# confirmation : la recharge en monnaie federee, la validation d'une adhesion
# payee en ligne. Sans `stripe listen`, ce rappel n'arrive jamais.
#
# Ils tournent a chaque `make e2e` : aucun n'est ignore. scripts/lancer_tests.sh
# regarde si `stripe listen` tourne sur l'hote et le dit par STRIPE_LISTEN. S'il
# manque, ces tests ECHOUENT tout de suite, avec la vraie raison, au lieu
# d'attendre leur delai pour un echec incomprehensible.
#
# / Some journeys only complete when Stripe calls the confirmation webhook back.
# They run on every `make e2e`: none is skipped. Without `stripe listen` they FAIL
# at once with the real reason (STRIPE_LISTEN is set by scripts/lancer_tests.sh).


def pytest_runtest_setup(item):
    """Fait echouer un test `stripe_listen` quand `stripe listen` ne tourne pas.
    / Fails a `stripe_listen` test when `stripe listen` is not running."""
    if not item.get_closest_marker("stripe_listen"):
        return
    if os.environ.get("STRIPE_LISTEN") != "1":
        pytest.fail(
            "`stripe listen` ne tourne pas : le lancer dans byobu, puis relancer make e2e. "
            "Ce parcours attend le webhook de confirmation de Stripe."
        )
