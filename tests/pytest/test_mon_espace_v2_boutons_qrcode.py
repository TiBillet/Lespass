"""
Les boutons de paiement par QR code dans « Mon espace » (skin V2), et les défauts D1 à D4.
/ QR code payment buttons in "My space" (V2 skin), and defects D1 to D4.

LOCALISATION : tests/pytest/test_mon_espace_v2_boutons_qrcode.py

RÈGLE MÉTIER TESTÉE
Spec : TECH_DOC/SESSIONS/SKINS/CHANTIER-10-V2-BOUTONS-QRCODE-MON-ESPACE.md §0, §5, §7.1, §7.2,
brief TECH_DOC/SESSIONS/FEDOW_IMPORT/briefs/10-1.md.
- « Initier un paiement » (bandeau `compte-initier-paiement`) est en tête du module
  « Mes responsabilités » de /my_account/. Il s'affiche EXACTEMENT quand la permission des
  routes du générateur l'autorise (`CanInitiatePaymentPermissionWithRequest`) : admin du lieu,
  droit `initiate_payment` sur le lieu, ou superuser — même hors `client_admin` (D3).
  Le module s'affiche aussi pour un·e caissier·e qui n'administre aucun lieu.
  Administrer un AUTRE lieu ne donne pas le bouton.
- « Scanner un QR code de paiement » (`compte-scanner-qrcode`) est sous « Ma carte », avec ou
  sans carte liée, quand l'email est validé. Sinon : un bouton gris, désactivé, sans lien (D4).
- En V2, /my_account/balance/ n'a plus ces deux boutons. Le skin classic les garde.
- D1 : la route /my_account/tirelire_section/ n'existe plus ; le partiel n'a plus de
  `</section>` orphelin.
- D2 : le scanner n'a plus de formulaire de repli (`#form-qrcode-scan`, `#qrcode-content`) ni
  de branche `qrcode_processed` ; un contenu qui n'est pas une adresse web affiche un message.
/ Business rules: who sees which button, where, and the four fixed defects.

SIMULATIONS
- Le skin est simulé : `BaseBillet.views.get_skin_courant` patché (« V2 » ou « reunion »).
  Le skin n'est jamais lu ni écrit en base (`ConfigurationSite.get_solo()` créerait la ligne
  et passe par le cache partagé avec le serveur, tests/PIEGES.md 9.86).
- Le Fedow distant est simulé : `BaseBillet.views.FedowAPI` patché (le nom importé en tête de
  BaseBillet/views.py, celui que `MyAccount` utilise). « Sans carte » = `[]` (un `MagicMock`
  nu serait vrai et rendrait la branche « avec carte »).
- Tout se passe dans le lieu dédié `test_mon_espace_v2_qrcode` (`FastTenantTestCase`, schéma
  cloné). Chaque test tourne dans une transaction annulée à la fin : utilisateurs, droits et
  sessions disparaissent seuls. Rien n'est écrit dans `lespass` ni dans un lieu de démo.
- La `Configuration` du lieu dédié est créée par `bulk_create()` si elle manque, jamais par
  `save()` (qui écrirait memcached, tests/PIEGES.md 13.22). Les caches des singletons lus par
  la page sont vidés avant et après chaque test.
/ Skin and Fedow are mocked; everything happens in a dedicated test venue, rolled back.

Lancer / Run : make test ARGS="tests/pytest/test_mon_espace_v2_boutons_qrcode.py"
"""

import uuid
from html.parser import HTMLParser
from unittest.mock import MagicMock, patch

from django.db import connection
from django.template.loader import get_template
from django.urls import reverse
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient

from AuthBillet.models import TibilletUser
from BaseBillet.models import Configuration, FormbricksConfig
from Customers.models import Client
from crowds.models import CrowdConfig

URL_DU_GENERATEUR = "/qrcodescanpay/get_generator/"
URL_DU_SCANNER = "/qrcodescanpay/get_scanner/"


# --------------------------------------------------------------------------- #
#  Lecture du HTML rendu / Reading the rendered HTML                           #
# --------------------------------------------------------------------------- #


class CollecteurDeBalises(HTMLParser):
    """
    Relève chaque balise ouvrante du HTML : son nom et ses attributs.
    / Collects every opening tag of the HTML: its name and attributes.
    """

    def __init__(self):
        super().__init__()
        self.balises = []

    def handle_starttag(self, tag, attrs):
        self.balises.append((tag, dict(attrs)))


def balise_par_testid(html, testid):
    """
    Rend `(nom_de_balise, attributs)` du premier élément qui porte ce `data-testid`,
    ou `None` s'il n'y en a pas.
    / Returns (tag, attributes) of the first element with this data-testid, or None.
    """
    collecteur = CollecteurDeBalises()
    collecteur.feed(html)
    for nom_de_balise, attributs in collecteur.balises:
        if attributs.get("data-testid") == testid:
            return nom_de_balise, attributs
    return None


def faux_fedow(avec_une_carte):
    """
    Un faux client Fedow : aucune monnaie, avec ou sans carte liée.
    / A fake Fedow client: no currency, with or without a linked card.
    """
    faux_client_fedow = MagicMock()
    if avec_une_carte:
        faux_client_fedow.NFCcard.retrieve_card_by_signature.return_value = [
            {"number_printed": "TEST0001"}
        ]
    else:
        faux_client_fedow.NFCcard.retrieve_card_by_signature.return_value = []
    faux_client_fedow.wallet.cached_retrieve_by_signature.return_value.validated_data = {
        "tokens": []
    }
    return patch("BaseBillet.views.FedowAPI", return_value=faux_client_fedow)


class TestMonEspaceV2BoutonsQrCode(FastTenantTestCase):
    """
    Les deux boutons de paiement par QR code et les défauts D1 à D4, dans le lieu dédié.
    / The two QR code payment buttons and defects D1 to D4, in the dedicated venue.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_mon_espace_v2_qrcode"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-mon-espace-v2-qrcode.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test mon espace V2 QR code"

    def setUp(self):
        # La transaction du test précédent a été annulée : on se replace sur le lieu.
        # / Back on the venue after the previous rolled-back test.
        connection.set_tenant(self.tenant)
        self.vider_les_caches_des_singletons()

        # Un schéma cloné n'a pas de ligne de Configuration : on la crée par
        # `bulk_create()` (jamais `save()`, qui écrirait memcached).
        # / A cloned schema has no Configuration row: bulk_create, never save().
        if Configuration.objects.first() is None:
            Configuration.objects.bulk_create(
                [
                    Configuration(
                        pk=Configuration.singleton_instance_id,
                        organisation="Test mon espace V2 QR code",
                        slug="test-mon-espace-v2-qrcode",
                    )
                ]
            )

    def tearDown(self):
        # La page a pu remplir le cache des singletons avec des lignes que l'annulation
        # va effacer. / The page may have cached rows the rollback will erase.
        connection.set_tenant(self.tenant)
        self.vider_les_caches_des_singletons()

    # ------------------------------------------------------------------ #
    #  Outils / Helpers                                                   #
    # ------------------------------------------------------------------ #

    def vider_les_caches_des_singletons(self):
        """
        Vide le cache des singletons que `get_context()` lit par `get_solo()`.
        / Clears the cache of the singletons get_context() reads with get_solo().
        """
        Configuration.clear_cache()
        CrowdConfig.clear_cache()
        FormbricksConfig.clear_cache()

    def creer_un_utilisateur(
        self, prefixe_de_l_email, email_valide=True, est_superuser=False
    ):
        """
        Un utilisateur humain actif, à l'email unique, créé dans la transaction du test.
        / An active human user with a unique email, created inside the test transaction.
        """
        email_unique = (
            f"{prefixe_de_l_email}-{uuid.uuid4().hex[:12]}@tibillet.localhost"
        )
        return TibilletUser.objects.create(
            email=email_unique,
            username=email_unique,
            espece=TibilletUser.TYPE_HUM,
            is_active=True,
            email_valid=email_valide,
            is_superuser=est_superuser,
            is_staff=est_superuser,
        )

    def page_rendue(self, utilisateur, chemin, skin="V2", avec_une_carte=False):
        """
        Rend la page `chemin` pour cet utilisateur, avec le skin et le Fedow simulés.
        Rend `(code_http, html)`.
        / Renders the page for this user with mocked skin and Fedow.
        """
        navigateur = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE="fr")
        navigateur.force_login(utilisateur)
        with patch("BaseBillet.views.get_skin_courant", return_value=skin):
            with faux_fedow(avec_une_carte=avec_une_carte):
                reponse = navigateur.get(chemin)
        return reponse.status_code, reponse.content.decode()

    def un_autre_lieu(self):
        """
        Un autre lieu, avec un domaine principal (le module l'affiche). Seul un lien
        `client_admin` vers lui est écrit, dans la transaction du test.
        / Another venue with a primary domain; only a client_admin link is written.
        """
        autre_lieu = (
            Client.objects.exclude(pk=self.tenant.pk)
            .exclude(schema_name__in=["public", "lespass"])
            .filter(domains__is_primary=True)
            .first()
        )
        assert autre_lieu is not None, (
            "Aucun autre lieu avec un domaine principal en base : lancer la démo "
            "(manage.py demo_data_v2)."
        )
        return autre_lieu

    # ------------------------------------------------------------------ #
    #  §7.1 — « Initier un paiement » sur l'index V2                      #
    # ------------------------------------------------------------------ #

    def test_admin_du_lieu_voit_le_bandeau_initier_un_paiement(self):
        """L'admin du lieu voit le bandeau, et son bouton mène au générateur.
        / The venue admin sees the banner; its button leads to the generator."""
        administrateur = self.creer_un_utilisateur("admin-qrcode")
        administrateur.client_admin.add(self.tenant)

        code_http, html = self.page_rendue(administrateur, "/my_account/")

        assert code_http == 200
        assert balise_par_testid(html, "compte-initier-paiement") is not None
        bouton = balise_par_testid(html, "compte-initier-paiement-bouton")
        assert bouton is not None
        assert bouton[0] == "a"
        assert (
            bouton[1]["href"]
            == reverse("qrcodescanpay-get-generator")
            == URL_DU_GENERATEUR
        )

    def test_caissiere_sans_lieu_administre_voit_le_module_et_le_bouton(self):
        """Droit `initiate_payment` seul : le module « Mes responsabilités » s'affiche,
        avec le bandeau. / Payment right only: the module shows, with the banner."""
        caissiere = self.creer_un_utilisateur("caisse-qrcode")
        caissiere.initiate_payment.add(self.tenant)

        code_http, html = self.page_rendue(caissiere, "/my_account/")

        assert code_http == 200
        assert balise_par_testid(html, "module-responsabilites") is not None
        assert balise_par_testid(html, "compte-initier-paiement") is not None

    def test_simple_adherent_ne_voit_ni_le_module_ni_le_bouton(self):
        """Ni admin, ni droit de paiement : pas de module, pas de bandeau.
        / Neither admin nor payment right: no module, no banner."""
        adherent = self.creer_un_utilisateur("adherent-qrcode")

        code_http, html = self.page_rendue(adherent, "/my_account/")

        assert code_http == 200
        assert balise_par_testid(html, "module-responsabilites") is None
        assert balise_par_testid(html, "compte-initier-paiement") is None
        assert URL_DU_GENERATEUR not in html

    def test_admin_d_un_autre_lieu_voit_le_module_sans_le_bouton(self):
        """Admin d'un AUTRE lieu seulement : le module liste ce lieu, mais le bandeau
        porte sur le lieu courant et ne s'affiche pas.
        / Admin of ANOTHER venue only: module shown, banner absent."""
        administrateur_ailleurs = self.creer_un_utilisateur("admin-ailleurs-qrcode")
        administrateur_ailleurs.client_admin.add(self.un_autre_lieu())

        code_http, html = self.page_rendue(administrateur_ailleurs, "/my_account/")

        assert code_http == 200
        assert balise_par_testid(html, "module-responsabilites") is not None
        assert balise_par_testid(html, "compte-initier-paiement") is None
        assert URL_DU_GENERATEUR not in html

    def test_superuser_hors_client_admin_voit_le_bouton(self):
        """D3 : un superuser absent de `client_admin` du lieu peut encaisser (permission
        des routes) : il voit le bandeau. / D3: superuser outside client_admin sees it."""
        superuser = self.creer_un_utilisateur("superuser-qrcode", est_superuser=True)
        assert not superuser.client_admin.filter(pk=self.tenant.pk).exists()

        code_http, html = self.page_rendue(superuser, "/my_account/")

        assert code_http == 200
        assert balise_par_testid(html, "compte-initier-paiement") is not None

    # ------------------------------------------------------------------ #
    #  §7.1 — « Scanner un QR code de paiement » sous « Ma carte »        #
    # ------------------------------------------------------------------ #

    def test_email_valide_sans_carte_voit_le_bouton_scanner(self):
        """Sans carte liée, le bouton est là : payer par QR code débite la tirelire.
        / No linked card: the button is still there."""
        adherent = self.creer_un_utilisateur("scan-sans-carte")

        code_http, html = self.page_rendue(
            adherent, "/my_account/", avec_une_carte=False
        )

        assert code_http == 200
        assert balise_par_testid(html, "compte-carte-vide") is not None
        bouton = balise_par_testid(html, "compte-scanner-qrcode")
        assert bouton is not None
        assert bouton[0] == "a"
        assert (
            bouton[1]["href"] == reverse("qrcodescanpay-get-scanner") == URL_DU_SCANNER
        )

    def test_email_valide_avec_carte_voit_le_bouton_scanner(self):
        """Avec une carte liée, le bouton est là aussi.
        / With a linked card, the button is there too."""
        adherent = self.creer_un_utilisateur("scan-avec-carte")

        code_http, html = self.page_rendue(
            adherent, "/my_account/", avec_une_carte=True
        )

        assert code_http == 200
        assert balise_par_testid(html, "compte-carte") is not None
        assert balise_par_testid(html, "compte-scanner-qrcode") is not None

    def test_email_non_valide_voit_un_bouton_gris_desactive_sans_lien(self):
        """D4 : email non validé = bouton gris, désactivé, sans lien vers le scanner.
        / D4: unvalidated email = grey, disabled button, no link."""
        adherent = self.creer_un_utilisateur(
            "scan-email-non-valide", email_valide=False
        )

        code_http, html = self.page_rendue(adherent, "/my_account/")

        assert code_http == 200
        assert balise_par_testid(html, "compte-scanner-qrcode") is None
        bouton_gris = balise_par_testid(html, "compte-scanner-qrcode-email-non-valide")
        assert bouton_gris is not None
        assert bouton_gris[0] == "button"
        assert "disabled" in bouton_gris[1]
        assert "href" not in bouton_gris[1]
        assert URL_DU_SCANNER not in html

    # ------------------------------------------------------------------ #
    #  §5.4 — /my_account/balance/ : V2 sans les boutons, classic avec    #
    # ------------------------------------------------------------------ #

    def test_balance_v2_n_a_plus_les_deux_boutons(self):
        """En V2, les deux gestes sont sur /my_account/ : la balance ne les répète pas.
        / In V2 the balance page no longer repeats the two buttons."""
        administrateur = self.creer_un_utilisateur("balance-v2")
        administrateur.client_admin.add(self.tenant)

        code_http, html = self.page_rendue(
            administrateur, "/my_account/balance/", skin="V2"
        )

        assert code_http == 200
        assert balise_par_testid(html, "account-tokens-table") is not None
        assert URL_DU_GENERATEUR not in html
        assert URL_DU_SCANNER not in html

    def test_balance_classic_garde_les_deux_boutons(self):
        """Non-régression : le skin classic garde « Initier un paiement » et le scanner.
        / Non-regression: the classic skin keeps both buttons."""
        administrateur = self.creer_un_utilisateur("balance-classic")
        administrateur.client_admin.add(self.tenant)

        code_http, html = self.page_rendue(
            administrateur, "/my_account/balance/", skin="reunion"
        )

        assert code_http == 200
        assert URL_DU_GENERATEUR in html
        bouton_scanner = balise_par_testid(html, "tirelire-scanner-qrcode")
        assert bouton_scanner is not None
        assert bouton_scanner[1]["href"] == URL_DU_SCANNER

    def test_balance_classic_superuser_hors_client_admin_voit_initier_un_paiement(self):
        """D3 sur classic : la balance lit le même booléen que l'index V2.
        / D3 on classic: the balance reads the same boolean."""
        superuser = self.creer_un_utilisateur("balance-superuser", est_superuser=True)

        code_http, html = self.page_rendue(
            superuser, "/my_account/balance/", skin="reunion"
        )

        assert code_http == 200
        assert URL_DU_GENERATEUR in html

    def test_balance_classic_email_non_valide_bouton_gris_desactive(self):
        """D4 sur le partiel partagé : bouton gris désactivé, plus de `<a href="">`.
        / D4 on the shared partial: disabled grey button, no more empty link."""
        adherent = self.creer_un_utilisateur(
            "balance-email-non-valide", email_valide=False
        )

        code_http, html = self.page_rendue(
            adherent, "/my_account/balance/", skin="reunion"
        )

        assert code_http == 200
        bouton_gris = balise_par_testid(
            html, "tirelire-scanner-qrcode-email-non-valide"
        )
        assert bouton_gris is not None
        assert bouton_gris[0] == "button"
        assert "disabled" in bouton_gris[1]
        assert 'href=""' not in html

    # ------------------------------------------------------------------ #
    #  §7.2 — Défauts D1 et D2                                            #
    # ------------------------------------------------------------------ #

    def test_d1_la_route_tirelire_section_n_existe_plus(self):
        """D1 : la route morte /my_account/tirelire_section/ répond 404.
        / D1: the dead route answers 404."""
        adherent = self.creer_un_utilisateur("d1-route")

        code_http, _html = self.page_rendue(adherent, "/my_account/tirelire_section/")

        assert code_http == 404

    def test_d1_le_partiel_tirelire_n_a_plus_de_section_orpheline(self):
        """D1 : autant de `<section` que de `</section>` dans le partiel.
        / D1: as many opening as closing section tags in the partial."""
        gabarit = get_template("htmx/views/my_account/tirelire_section.html")
        with open(gabarit.origin.name, encoding="utf-8") as fichier:
            source_du_partiel = fichier.read()

        assert source_du_partiel.count("<section") == source_du_partiel.count(
            "</section>"
        )

    def test_d2_le_scanner_n_a_plus_de_formulaire_de_repli(self):
        """D2 : plus de formulaire `#form-qrcode-scan` (il répondait 405), plus de
        `#qrcode-content` lu par le script, plus de branche `qrcode_processed`. Un contenu
        qui n'est pas une adresse web affiche un message.
        / D2: no fallback form, no hidden input read by the script, no dead branch."""
        gabarit = get_template("fonctionnel/qrcode_scan_pay/scanner.html")
        with open(gabarit.origin.name, encoding="utf-8") as fichier:
            source_du_scanner = fichier.read()

        assert "form-qrcode-scan" not in source_du_scanner
        assert "qrcode-content" not in source_du_scanner
        assert "qrcode_processed" not in source_du_scanner
        assert "scan-result-not-payment" in source_du_scanner

    def test_d2_la_page_du_scanner_se_rend_sans_formulaire(self):
        """D2 : la page du scanner se rend (email validé) et n'a pas de formulaire.
        / D2: the scanner page renders without a form."""
        adherent = self.creer_un_utilisateur("d2-scanner")

        code_http, html = self.page_rendue(adherent, URL_DU_SCANNER)

        assert code_http == 200
        assert balise_par_testid(html, "scanner-qrcode-pas-un-paiement") is not None
        assert 'id="form-qrcode-scan"' not in html
