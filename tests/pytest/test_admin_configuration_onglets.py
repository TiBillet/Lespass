"""
La page « Paramètres » en onglets, et l'accès aux pages voisines.
/ The Settings page as tabs, and access to its sibling pages.

LOCALISATION : tests/pytest/test_admin_configuration_onglets.py

CE QUE CES TESTS PROTEGENT
--------------------------

1. LE DECOUPAGE EN ONGLETS ne doit RIEN changer d'autre. Les 4 sections de
   ConfigurationAdmin existaient deja ; on ne fait que les rendre en onglets.
   Il a ete decide de n'exposer AUCUN des 45 champs invisibles de
   Configuration. Le risque numero un est donc qu'un champ apparaisse ou
   disparaisse par accident en manipulant les fieldsets — d'ou un test qui
   compare la liste exacte.
   / Turning sections into tabs must change nothing else: no field may appear
     or disappear.

2. UN ONGLET INATTEIGNABLE. C'est le bug reel qui a motive ce lot : le groupe
   « Parametres / Cles API / Webhooks » existait, mais la barre ne s'affichait
   PAS sur la page Parametres — la seule des trois presente dans le rail. On ne
   pouvait donc atteindre « Cles API » que par la recherche.

   La cause est dans Unfold (_get_tabs_list, unfold/templatetags/unfold.py) :

       if isinstance(tab_model, str):
           if str(opts) == tab_model and page == "changelist":

   Une entree ECRITE EN CHAINE ne vaut que pour une changelist. Or
   Configuration et FormbricksConfig sont des singletons django-solo : ils
   rendent un FORMULAIRE a l'URL de liste. Il leur faut une entree dict portant
   « detail »: True.
   / A string entry only matches changelists; both singletons render a form at
     their list URL, so their tab bar never appeared.

   Le dernier test de ce fichier est generique : il echoue des qu'UN modele
   cite dans un groupe d'onglets ne rend pas la barre sur sa propre page. C'est
   lui qui empeche le cul-de-sac de revenir par une autre porte.

Meme pattern que les autres tests d'admin : base de dev vivante.
"""

import pytest
from django.test import Client as HttpClient
from django.urls import NoReverseMatch, reverse
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from Customers.models import Client


# Les 24 champs exposes AVANT le passage en onglets. Ecrits en dur, et c'est
# volontaire : les relire depuis la classe testee ne prouverait rien (le test
# suivrait la regression). C'est un releve, pas un calcul.
# / Hard-coded on purpose: reading them from the class under test would make
#   the test follow any regression instead of catching it.
CHAMPS_ATTENDUS = [
    # Identite du lieu
    "organisation",
    "short_description",
    "long_description",
    "img",
    "logo",
    "postal_address",
    "phone",
    "email",
    "site_web",
    # Reglages
    "fuseau_horaire",
    "language",
    "jauge_max",
    "allow_concurrent_bookings",
    "currency_code",
    # Personnalisation
    "event_menu_name",
    "membership_menu_name",
    "description_membership_page",
    "description_event_page",
    "first_input_label_membership",
    "second_input_label_membership",
    "additional_text_in_membership_mail",
    # Paiement (Stripe)
    "onboard_stripe",
    "stripe_invoice",
    "stripe_accept_sepa",
]


@pytest.fixture(scope="session")
def django_db_setup():
    # Reutilise la base de dev (pas de creation de test DB).
    # / Reuse the dev database.
    pass


@pytest.fixture
def lieu_et_superadmin(db):
    """Le premier lieu qui a un domaine ET un superadmin."""
    for tenant in Client.objects.exclude(schema_name="public"):
        domaine = tenant.domains.first()
        if not domaine:
            continue
        with tenant_context(tenant):
            utilisateur = TibilletUser.objects.filter(is_superuser=True).first()
        if utilisateur:
            return tenant, domaine.domain, utilisateur
    pytest.skip("Aucun lieu avec un domaine et un superadmin.")


@pytest.fixture
def navigateur(lieu_et_superadmin):
    _tenant, domaine, utilisateur = lieu_et_superadmin
    client = HttpClient(HTTP_HOST=domaine)
    client.force_login(utilisateur)
    return client


def _fieldsets_de_la_configuration():
    from Administration.admin_tenant import ConfigurationAdmin

    return ConfigurationAdmin.fieldsets


# --------------------------------------------------------------------------- #
# Volet 1 — les quatre onglets                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_aucun_champ_n_apparait_ni_ne_disparait():
    """
    LE test du lot. On a decide de n'exposer aucun champ supplementaire : la
    liste doit donc etre identique, dans le meme ordre.
    / The decisive test: no field may be added or removed.
    """
    champs = [
        champ
        for _titre, options in _fieldsets_de_la_configuration()
        for champ in options["fields"]
    ]
    assert champs == CHAMPS_ATTENDUS, (
        "La liste des champs exposes a change. Le decoupage en onglets ne doit "
        "etre qu'une mise en forme.\n"
        f"  apparus  : {sorted(set(champs) - set(CHAMPS_ATTENDUS))}\n"
        f"  disparus : {sorted(set(CHAMPS_ATTENDUS) - set(champs))}"
    )


@pytest.mark.django_db
def test_les_quatre_sections_sont_des_onglets():
    """
    Unfold ne transforme un fieldset en onglet que s'il porte
    classes:["tab"] ET UN NOM (filtre `tabs`, unfold/templatetags/unfold.py).
    Une section anonyme se rendrait AU-DESSUS de la barre, pas dedans — c'est
    le piege que ce test verrouille.
    / A fieldset becomes a tab only with classes:["tab"] AND a name.
    """
    fieldsets = _fieldsets_de_la_configuration()
    assert len(fieldsets) == 4

    for titre, options in fieldsets:
        assert "tab" in options.get("classes", []), (
            f"Section « {titre} » sans classe tab."
        )
        assert titre, "Une section sans nom ne peut pas devenir un onglet."


@pytest.mark.django_db
def test_les_titres_des_onglets_sont_traduisibles():
    """
    Deux titres etaient des chaines brutes ('Options générales',
    'Personnalisation'). Une chaine nue ne passe jamais par makemessages.
    / Two titles were raw strings and never reached makemessages.
    """
    from django.utils.functional import Promise

    for titre, _options in _fieldsets_de_la_configuration():
        assert isinstance(titre, Promise), (
            f"Le titre « {titre} » est une chaine brute : il ne sera jamais traduit."
        )


@pytest.mark.django_db
def test_la_page_des_parametres_repond_et_rend_ses_onglets(navigateur):
    """
    Rappel : cette page a deja ete mise en 500 par un __str__ paresseux
    (`fix-configuration-str-lazy`). On verifie qu'elle repond, pas seulement
    que les fieldsets sont bien formes en Python.
    / This page was once 500ing; check it actually renders.
    """
    reponse = navigateur.get("/admin/BaseBillet/configuration/")
    assert reponse.status_code == 200
    html = reponse.content.decode()
    assert "activeFieldsetTab" in html, "Les onglets de fieldset ne sont pas rendus."


# --------------------------------------------------------------------------- #
# Volet 2 — aucun onglet ne doit etre inatteignable                            #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_la_page_des_parametres_mene_a_ses_pages_voisines(navigateur):
    """
    Le bug signale : depuis « Parametres », on ne pouvait aller ni vers
    « Cles API » ni vers « Webhooks ». La barre ne s'affichait pas.
    / The reported bug: no way from Settings to its sibling pages.
    """
    html = navigateur.get("/admin/BaseBillet/configuration/").content.decode()
    assert "tabs-wrapper" in html, (
        "Pas de barre d'onglets sur la page Parametres : « Cles API » et "
        "« Webhooks » redeviennent inatteignables."
    )
    for cible in ("/admin/BaseBillet/externalapikey/", "/admin/BaseBillet/webhook/"):
        assert cible in html, f"Lien absent vers {cible}"
        assert navigateur.get(cible).status_code == 200, f"{cible} ne repond pas"


@pytest.mark.django_db
def test_aucun_onglet_declare_n_est_inatteignable(navigateur, lieu_et_superadmin):
    """
    Le garde-fou generique, et le plus important du fichier.

    Pour CHAQUE modele cite dans un groupe d'onglets, la barre doit s'afficher
    sur sa propre page. Sinon ce modele devient un cul-de-sac : on peut y
    arriver, mais pas en repartir vers ses voisins.

    Ce test attrape la classe entiere du bug — y compris sur un groupe ajoute
    demain, et y compris si quelqu'un ajoute un singleton en oubliant l'entree
    « detail »: True.

    Il balaie _onglets_hors_modules() ET get_tabs(). La premiere version ne
    regardait que la premiere : le meme defaut vivait dans la seconde, sur les
    pages de configuration des modules (ConfigurationSite, CrowdConfig...), et
    est passe entre les mailles.
    / The generic guard: every model listed in a tab group must render the bar
      on its own page, or it becomes a dead end.
    """
    from django.test import RequestFactory

    from Administration.admin.dashboard import _onglets_hors_modules, get_tabs

    # On balaie les DEUX sources de barres d'onglets. Ne regarder que
    # _onglets_hors_modules() etait l'angle mort : le meme defaut existait dans
    # get_tabs(), qui construit les barres de TOUS les modules, et il a survecu
    # a la premiere correction.
    # / Both sources are swept: looking only at the first one was the blind spot
    #   that let the same defect survive in get_tabs().
    tenant, _domaine, utilisateur = lieu_et_superadmin
    requete = RequestFactory().get("/admin/")
    requete.user = utilisateur
    with tenant_context(tenant):
        groupes = list(_onglets_hors_modules()) + list(get_tabs(requete))

    culs_de_sac = []
    en_erreur = []
    for groupe in groupes:
        for modele in groupe.get("models", []):
            nom = modele["name"] if isinstance(modele, dict) else modele
            app_label, model_name = nom.split(".")
            try:
                url = reverse(f"staff_admin:{app_label}_{model_name}_changelist")
            except NoReverseMatch:
                continue
            # raise_request_exception=False : une page d'admin qui plante pour
            # une raison etrangere aux onglets ne doit pas faire echouer CE
            # test, qui n'a qu'un seul travail. On les recense a part.
            # Cas connu : AssetAdmin.get_queryset() fait un appel reseau a
            # Fedow (admin_tenant.py:4264) et peut lever hors ligne.
            # / An admin failing for unrelated reasons must not fail this test.
            navigateur.raise_request_exception = False
            try:
                reponse = navigateur.get(url)
            except Exception:
                en_erreur.append(nom)
                continue
            finally:
                navigateur.raise_request_exception = True

            if reponse.status_code != 200:
                en_erreur.append(f"{nom} ({reponse.status_code})")
                continue
            if "tabs-wrapper" not in reponse.content.decode():
                culs_de_sac.append(nom)

    assert not culs_de_sac, (
        f"Ces pages ne rendent pas leur barre d'onglets : {sorted(set(culs_de_sac))}. "
        "Un singleton django-solo rend un FORMULAIRE a l'URL de liste : il lui "
        'faut une entree {"name": ..., "detail": True} dans le groupe.'
    )

    # On ne fait pas echouer le test la-dessus — ce n'est pas son sujet — mais
    # on le rend visible plutot que de l'avaler en silence.
    # / Reported, not asserted: it is not this test's job.
    if en_erreur:
        import warnings

        warnings.warn(
            "Pages d'onglets injoignables pour une raison etrangere aux onglets "
            f"(a instruire separement) : {sorted(set(en_erreur))}",
            stacklevel=2,
        )
