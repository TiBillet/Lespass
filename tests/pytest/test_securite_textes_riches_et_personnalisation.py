"""
Sécurité des textes riches, personnalisation des pages, action d'approbation, alignement
du rapport comptable.
/ Rich text security, page customization, approval action, accounting report alignment.

LOCALISATION : tests/pytest/test_securite_textes_riches_et_personnalisation.py

Code testé :
- Administration/utils.py : clean_html (filtre des images vers l'admin)
- Administration/admin/resources.py : ResourceAdmin.save_model (nettoyage XSS)
- BaseBillet/views.py : noms de menu personnalisés (get_context, FederationViewset)
- booking/templates : textes d'introduction des pages Ressources et Bénévolat
- Administration/admin_tenant.py : EventAdmin.approuver_proposition (action de ligne)
- comptabilite/presentation.py : _tableau (alignement des colonnes)

Les tests qui écrivent dans la Configuration du lieu `lespass` remettent les champs à
vide dans un `finally` : la base de dev est partagée, sans rollback.
/ Tests writing the `lespass` Configuration reset the fields in a `finally`.
"""
import uuid

import pytest
from django.test import Client as DjangoClient
from django.urls import reverse
from django.utils import timezone
from django_tenants.utils import tenant_context

HOTE_DU_LIEU = "lespass.tibillet.localhost"
CHARGE_XSS = '"><script>alert(66)</script>'


# --------------------------------------------------------------------------- #
# clean_html : les images ne doivent jamais viser l'admin                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "adresse_de_l_image",
    [
        "/admin/BaseBillet/event/x/archive/",
        "/%61dmin/BaseBillet/event/x/archive/",
        "/./admin/x/",
        "/%2e/admin/x/",
        "../admin/x/",
        "../../%2e%2e/admin/x/",
        "\\admin/x/",
        "/ad\tmin/x/",
        "https://lespass.tibillet.localhost/%61dmin/x/",
        "/logout/",
    ],
)
def test_clean_html_retire_les_images_qui_visent_l_admin_meme_deguisees(adresse_de_l_image):
    """
    Une image dont l'adresse mène à l'admin (ou à la déconnexion) perd son src, même
    encodée (%61), normalisée (/./), relative (../) ou avec « \\ » et tabulation.
    / An image pointing to the admin loses its src, even disguised.
    """
    from Administration.utils import clean_html

    html_nettoye = clean_html(f'<img src="{adresse_de_l_image}">')

    assert "src=" not in html_nettoye


@pytest.mark.parametrize(
    "adresse_de_l_image",
    [
        "/media/images/photo.jpg",
        "https://exemple.org/img/a.png",
        "images/a.png",
    ],
)
def test_clean_html_garde_les_images_ordinaires(adresse_de_l_image):
    """Une image ordinaire garde son src. / A regular image keeps its src."""
    from Administration.utils import clean_html

    html_nettoye = clean_html(f'<img src="{adresse_de_l_image}">')

    assert f'src="{adresse_de_l_image}"' in html_nettoye


# --------------------------------------------------------------------------- #
# Admin Resource : la description est nettoyée à l'enregistrement              #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_l_admin_ressource_nettoie_la_description_a_l_enregistrement(tenant, admin_client):
    """
    POST du formulaire admin d'une ressource avec <script> et onerror : la description
    enregistrée n'a plus ni l'un ni l'autre, et la page publique ne les affiche pas.
    / Admin POST with <script> and onerror: both are gone in DB and on the public page.
    """
    from booking.tests.test_booking_engine import (
        _cleanup,
        _make_calendar,
        _make_resource,
        _make_weekly_opening,
    )

    with tenant_context(tenant):
        try:
            ressource = _make_resource(
                "securite_description",
                _make_calendar("securite_description"),
                _make_weekly_opening("securite_description"),
            )
            adresse_du_formulaire = reverse("staff_admin:booking_resource_change", args=[ressource.pk])
            donnees_du_formulaire = {
                "name": ressource.name,
                "description": '<p>Salle <strong>calme</strong></p><script>alert(1)</script>'
                               '<img src="x.png" onerror="alert(2)">',
                "product": str(ressource.product_id),
                "calendar": str(ressource.calendar_id),
                "weekly_opening": str(ressource.weekly_opening_id),
                "capacity": "1",
                "cancellation_deadline_hours": "24",
                "booking_horizon_days": "28",
            }

            reponse = admin_client.post(adresse_du_formulaire, donnees_du_formulaire)
            assert reponse.status_code == 302, reponse.content[:800]

            ressource.refresh_from_db()
            assert "<strong>calme</strong>" in ressource.description
            assert "<script" not in ressource.description
            assert "onerror" not in ressource.description

            page_publique = DjangoClient(HTTP_HOST=HOTE_DU_LIEU).get(
                f"/booking/{ressource.pk}/resource/"
            ).content.decode()
            assert "<strong>calme</strong>" in page_publique
            assert "alert(1)" not in page_publique
            assert "alert(2)" not in page_publique
        finally:
            _cleanup()


# --------------------------------------------------------------------------- #
# Personnalisation des pages Ressources, Bénévolat et Réseau                   #
# --------------------------------------------------------------------------- #


MODULES_DES_PAGES = ("module_booking", "module_benevolat", "module_federation")


def _activer_les_modules_des_pages():
    """
    Active les trois modules et rend leur état d'origine, à rendre en fin de test.
    / Turns the three modules on and returns their original state.
    """
    from BaseBillet.models import Configuration

    configuration = Configuration.get_solo()
    etat_d_origine_des_modules = {}
    for nom_du_module in MODULES_DES_PAGES:
        etat_d_origine_des_modules[nom_du_module] = getattr(configuration, nom_du_module)
        setattr(configuration, nom_du_module, True)
    configuration.save()
    return etat_d_origine_des_modules


def _remettre_la_personnalisation_a_vide(etat_d_origine_des_modules=None):
    from BaseBillet.models import Configuration

    configuration = Configuration.get_solo()
    if etat_d_origine_des_modules:
        for nom_du_module, etat_d_origine in etat_d_origine_des_modules.items():
            setattr(configuration, nom_du_module, etat_d_origine)
    configuration.booking_menu_name = None
    configuration.benevolat_menu_name = None
    configuration.federation_menu_name = None
    configuration.description_booking_page = ""
    configuration.description_benevolat_page = ""
    configuration.save()


@pytest.mark.django_db
def test_les_noms_de_menu_personnalises_s_affichent_et_sont_echappes(tenant):
    """
    Un nom de menu contenant du HTML s'affiche échappé sur toutes les pages (menu,
    titre, h1, fil d'Ariane JSON-LD) : jamais de <script> brut.
    / A menu name with HTML is shown escaped everywhere: never a raw <script>.
    """
    from BaseBillet.models import Configuration

    with tenant_context(tenant):
        etat_d_origine_des_modules = _activer_les_modules_des_pages()
        try:
            configuration = Configuration.get_solo()
            configuration.booking_menu_name = f"Salles {CHARGE_XSS}"
            configuration.benevolat_menu_name = f"Coups de main {CHARGE_XSS}"
            configuration.federation_menu_name = f"Amis {CHARGE_XSS}"
            configuration.save()

            navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU)
            for adresse in ("/booking/", "/booking/benevolat/", "/federation/"):
                page = navigateur.get(adresse).content.decode()
                assert "<script>alert(66)" not in page, adresse
                assert "Salles &quot;&gt;&lt;script&gt;" in page, adresse
                assert "Coups de main &quot;&gt;&lt;script&gt;" in page, adresse
                assert "Amis &quot;&gt;&lt;script&gt;" in page, adresse
        finally:
            _remettre_la_personnalisation_a_vide(etat_d_origine_des_modules)


@pytest.mark.django_db
def test_les_textes_d_introduction_remplacent_le_texte_par_defaut(tenant):
    """
    Avec un texte : il s'affiche en haut de /booking/ et /booking/benevolat/.
    Sans texte : /booking/benevolat/ garde son chapô par défaut.
    / With a text it is shown; without, the volunteering page keeps its default.
    """
    from BaseBillet.models import Configuration

    chapo_par_defaut = "Les coups de main dont le lieu a besoin."

    with tenant_context(tenant):
        etat_d_origine_des_modules = _activer_les_modules_des_pages()
        try:
            _remettre_la_personnalisation_a_vide()

            navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU)
            assert chapo_par_defaut in navigateur.get("/booking/benevolat/").content.decode()
            assert 'data-testid="booking-description-page"' not in navigateur.get("/booking/").content.decode()

            configuration = Configuration.get_solo()
            configuration.description_booking_page = "<p>Intro des <b>salles</b></p>"
            configuration.description_benevolat_page = "<p>Intro des <b>bénévoles</b></p>"
            configuration.save()

            page_ressources = navigateur.get("/booking/").content.decode()
            page_benevolat = navigateur.get("/booking/benevolat/").content.decode()
            assert "Intro des <b>salles</b>" in page_ressources
            assert "Intro des <b>bénévoles</b>" in page_benevolat
            assert chapo_par_defaut not in page_benevolat
        finally:
            _remettre_la_personnalisation_a_vide(etat_d_origine_des_modules)


# --------------------------------------------------------------------------- #
# Action de ligne « Approuver et publier la proposition »                      #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_approuver_une_proposition_est_refuse_a_un_utilisateur_non_admin(tenant):
    """
    Un utilisateur connecté mais pas admin du lieu ne peut pas approuver : la
    proposition reste en attente.
    / A logged-in non-admin cannot approve: the proposal stays pending.
    """
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Event

    with tenant_context(tenant):
        utilisateur_ordinaire = TibilletUser.objects.create(
            email=f"non-admin-{uuid.uuid4().hex[:8]}@exemple.org",
            username=f"non-admin-{uuid.uuid4().hex[:8]}",
            espece=TibilletUser.TYPE_HUM,
            is_active=True,
        )
        proposition = Event.objects.create(
            name=f"ProposalTest non admin {uuid.uuid4().hex[:6]}",
            datetime=timezone.now() + timezone.timedelta(days=3),
            is_proposal=True,
            published=False,
        )
        try:
            navigateur = DjangoClient(HTTP_HOST=HOTE_DU_LIEU)
            navigateur.force_login(utilisateur_ordinaire)
            adresse_de_l_action = reverse(
                "staff_admin:BaseBillet_event_approuver_proposition", args=[proposition.pk]
            )

            reponse = navigateur.get(adresse_de_l_action)

            # L'admin redirige vers la connexion (302) ou refuse (403).
            # / The admin redirects to login (302) or refuses (403).
            assert reponse.status_code in (302, 403)
            proposition.refresh_from_db()
            assert proposition.is_proposal is True
            assert proposition.published is False
        finally:
            proposition.delete()
            utilisateur_ordinaire.delete()


# --------------------------------------------------------------------------- #
# Rapport comptable : un titre de colonne est aligné comme son contenu         #
# --------------------------------------------------------------------------- #


def test_une_colonne_de_nombres_est_alignee_a_droite_titre_compris():
    """Nombres et cases vides « — » : la colonne et son titre vont à droite.
    / Numbers and empty cells: column and header go right."""
    from comptabilite.presentation import _cellule_montant, _cellule_texte, _tableau

    tableau = _tableau(
        "", "essai", ["Libellé", "Montant"],
        [
            [_cellule_texte("Espèces"), _cellule_montant(1250)],
            [_cellule_texte("Chèque"), _cellule_texte("—")],
        ],
    )

    assert [entete["a_droite"] for entete in tableau["entetes"]] == [False, True]
    for ligne in tableau["lignes"]:
        assert ligne[0]["a_droite"] is False
        assert ligne[1]["a_droite"] is True


def test_une_colonne_mixte_est_alignee_a_gauche_partout():
    """Texte et nombres mêlés (la « Valeur » de l'en-tête) : tout à gauche.
    / Mixed text and numbers: everything left."""
    from comptabilite.presentation import _cellule_nombre, _cellule_texte, _tableau

    tableau = _tableau(
        "", "essai", ["Libellé", "Valeur"],
        [
            [_cellule_texte("Lieu"), _cellule_texte("Lespass")],
            [_cellule_texte("Numéro de clôture"), _cellule_nombre(12)],
        ],
    )

    assert tableau["entetes"][1]["a_droite"] is False
    assert tableau["lignes"][1][1]["a_droite"] is False


def test_une_ligne_plus_courte_que_les_colonnes_ne_plante_pas():
    """Une ligne qui a moins de cases que de colonnes est tolérée.
    / A row shorter than the header is tolerated."""
    from comptabilite.presentation import _cellule_montant, _cellule_texte, _tableau

    tableau = _tableau(
        "", "essai", ["Libellé", "Nombre", "Montant"],
        [
            [_cellule_texte("Avoirs"), _cellule_montant(300), _cellule_montant(300)],
            [_cellule_texte("Total")],
        ],
    )

    assert [entete["a_droite"] for entete in tableau["entetes"]] == [False, True, True]
