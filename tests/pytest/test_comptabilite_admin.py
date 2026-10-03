"""
tests/pytest/test_comptabilite_admin.py
L'admin des clôtures (`comptabilite.ClotureCaisse`) : la fiche d'une clôture, le rapport
temps réel, et la présentation des montants.
/ The closures admin: the closure detail page, the real-time report, and the display of
amounts.

LOCALISATION : tests/pytest/test_comptabilite_admin.py

RÈGLES MÉTIER TESTÉES (fiche F §2, §3)
- La fiche d'une clôture montre les sections du rapport stocké (`rapport_json`) dans
  l'ordre de la fiche : d'abord l'essentiel (en-tête, chiffre d'affaires, règlements,
  caisse espèces, réconciliation, offerts), puis, repliés, l'annexe, les points, la
  marge brute, le détail et l'intégrité.
- La caisse espèces n'existe que dans une J : une clôture mensuelle ne la montre pas.
- La phrase de réconciliation est écrite par l'affichage : « Argent reçu = ventes payées
  en argent + recharges − remboursements − cartes vidées ± écarts d'encaissement »,
  avec des montants POSITIFS après « − ».
- L'opérateur d'une correction est stocké par son identifiant, jamais par son email (le
  Z scellé ne garde aucune donnée personnelle lisible) ; l'affichage montre son nom (nom
  complet, sinon email), ou « compte supprimé » s'il n'existe plus.
- L'intégrité montre « OK », ou la liste des anomalies (numéro de vente, raison).
- Le rapport temps réel (X) lit le moteur unique (`RapportDesVentes.rapport_x()`) : il
  montre l'habitus des cartes et les opérateurs, jamais l'intégrité. Sa période par
  défaut est le service en cours : depuis la fin de la dernière J (sinon la première
  vente du lieu) jusqu'à maintenant. Les heures saisies et affichées sont en heure du
  lieu (`Configuration.fuseau_horaire`).
- Un montant s'écrit à la française : « 1 050,00 € » (espaces insécables).
- L'en-tête compte les « opérations numérotées » (toutes les ventes réglées), dont les
  avoirs, les cartes vidées et les corrections. L'offert des règlements s'appelle
  « Offert (bouton OFFRIR et cadeaux émis) ».
- Un Z s'affiche dans le fuseau figé dans son en-tête au calcul ; sans lui (ancienne
  clôture), dans le fuseau actuel du lieu. Un Z sans mentions légales s'affiche.
/ Business rules tested: section order, cash drawer only in a J, the reconciliation
sentence with positive amounts after "−", the operator's name, integrity, the X report,
French amounts, labels, frozen time zone.

POURQUOI PAS LE CLIENT DE TEST DJANGO
Le rendu complet d'une page d'admin Unfold avec `force_login` plante (bug connu,
indépendant de la comptabilité). On teste donc les méthodes de l'admin avec une
`RequestFactory`. Le gabarit de la fiche (`change_form_before.html`) est rendu avec le
contexte que `changeform_view` lui passe ; la vue du rapport temps réel rend elle-même
son gabarit.
/ Unfold admin pages crash with force_login in the test client: we call the admin
methods with a RequestFactory, then render the page templates with their context.

SCHÉMA DÉDIÉ
Une clôture lit TOUTES les ventes du lieu : il faut un lieu qui ne contient que les
ventes du test (`FastTenantTestCase`). Chaque test annule sa transaction à la fin. Le
singleton `LaboutikConfiguration` est créé en base (tests/PIEGES.md 9.86). La
`Configuration` du lieu est réécrite à chaque test : son cache survit à l'annulation.
Les ventes sont écrites PAR LE SERVICE (`fabriques_vente.py`), jamais à la main.
/ Dedicated schema; sales are written through the sale service.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-F-rapport-unique.md (§2, §3).

Lancer / Run : make test ARGS="tests/pytest/test_comptabilite_admin.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import copy  # noqa: E402
import re  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, time, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.contrib.admin.options import ModelAdmin as DjangoModelAdmin  # noqa: E402
from django.contrib.messages.storage.fallback import FallbackStorage  # noqa: E402
from django.contrib.sessions.middleware import SessionMiddleware  # noqa: E402
from django.db import connection  # noqa: E402
from django.http import HttpResponse  # noqa: E402
from django.template.loader import render_to_string  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.urls import NoReverseMatch, reverse  # noqa: E402
from django.utils import timezone, translation  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402

import comptabilite.tasks  # noqa: E402
from Administration.admin.site import staff_admin_site  # noqa: E402
from AuthBillet.models import TibilletUser, Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration,
    LigneArticle,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from BaseBillet.services_vente import (  # noqa: E402
    ajouter_reglement,
    ecrire_la_vente_d_avoir_d_une_ligne,
    encaisser_vente,
    ouvrir_vente,
)
from comptabilite.admin import ClotureCaisseAdmin  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from comptabilite.presentation import (  # noqa: E402
    euros_a_la_francaise,
    sections_pour_affichage,
)
from fabriques_panier import identifiant_unique, taches_celery_enregistrees  # noqa: E402
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fedow_core.models import Asset  # noqa: E402
from laboutik.models import LaboutikConfiguration, PointDeVente  # noqa: E402

FUSEAU_DE_PARIS = ZoneInfo("Europe/Paris")

# L'espace insécable : entre les milliers, et entre le nombre et « € ».
# / The non-breaking space: between thousands, and before "€".
ESPACE_INSECABLE = "\u00a0"

# Le signe moins typographique d'un montant négatif.
# / The typographic minus sign of a negative amount.
SIGNE_MOINS = "\u2212"

# Les sections d'une J, dans l'ordre de la fiche F §2 (data-testid du gabarit).
# / The sections of a J, in the order of sheet F §2 (template data-testid).
SECTIONS_ESSENTIELLES_D_UNE_J = [
    "en-tete",
    "chiffre-affaires",
    "reglements",
    "caisse-especes",
    "reconciliation",
    "offerts",
]
SECTIONS_REPLIEES_D_UNE_J = [
    "annexe",
    "points",
    "marge-brute",
    "detail",
    "integrite",
]


def heure_de_paris(annee, mois, jour, heure, minute=0):
    """Un moment en heure de Paris. / A moment in Paris time."""
    return datetime(annee, mois, jour, heure, minute, tzinfo=FUSEAU_DE_PARIS)


def euros(nombre_en_texte):
    """
    Un montant attendu, écrit à la main : « 1 050,00 » → « 1 050,00 € » avec les
    espaces insécables. Le texte est écrit par le test, jamais par le code testé.
    / An expected amount, hand-written, with non-breaking spaces.
    """
    nombre_avec_espaces_insecables = nombre_en_texte.replace(" ", ESPACE_INSECABLE)
    return f"{nombre_avec_espaces_insecables}{ESPACE_INSECABLE}€"


class TestComptabiliteAdmin(FastTenantTestCase):
    """
    La fiche d'une clôture, le rapport temps réel et les montants à la française.
    / The closure page, the real-time report and French amounts.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_comptabilite_admin"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-comptabilite-admin.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test comptabilite admin"

    def setUp(self):
        """
        Le lieu de test : son singleton de caisse, sa configuration (Paris, fermeture à
        2 h, aucun email de rapport), un jus à 3,50 €, un point de vente, un
        administrateur et l'admin des clôtures.
        / The test venue, a juice, a point of sale, an administrator, the closures admin.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse porte la clé des empreintes (tests/PIEGES.md 9.86).
        # / The register singleton carries the fingerprint key.
        LaboutikConfiguration.get_solo().save()

        # Toutes les valeurs lues par la clôture sont écrites ici : le cache de la
        # configuration garde les valeurs du test précédent.
        # / Every value read by the closure is written here (the cache survives).
        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.heure_de_fermeture = time(2, 0)
        configuration.rapport_emails = ""
        configuration.postal_address = None
        configuration.postal_code = None
        configuration.city = "Ville du lieu de test"
        configuration.siren = ""
        configuration.tva_number = ""
        configuration.phone = ""
        configuration.save()

        self.tarif_du_jus = creer_tarif_vendu(
            nom="Jus",
            prix_en_euros="3.50",
            taux_tva="20.00",
            methode_caisse=Product.VENTE,
        )
        self.point_de_vente = PointDeVente.objects.create(
            name="Bar", code_journal="", hidden=True
        )

        email_de_l_administrateur = f"admin-{identifiant_unique()}@tibillet.localhost"
        self.administrateur = TibilletUser.objects.create(
            email=email_de_l_administrateur,
            username=email_de_l_administrateur,
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        self.admin_des_clotures = ClotureCaisseAdmin(ClotureCaisse, staff_admin_site)
        self.fabrique_de_requetes = RequestFactory()

    # ------------------------------------------------------------------
    # Outils du test
    # / Test helpers
    # ------------------------------------------------------------------

    def _requete(self, chemin, parametres=None):
        """
        Une requête GET de l'administrateur, avec session et messages.
        / A GET request from the administrator, with session and messages.
        """
        if parametres is None:
            parametres = {}
        requete = self.fabrique_de_requetes.get(chemin, data=parametres)
        requete.user = self.administrateur
        SessionMiddleware(lambda requete_recue: None).process_request(requete)
        requete.session.save()
        requete._messages = FallbackStorage(requete)
        return requete

    def _monnaie_locale(self):
        """
        Une monnaie locale du moteur fedow_core, créée par le lieu de test.
        / A local currency created by the test venue.
        """
        portefeuille_d_origine = Wallet.objects.create(
            name=f"Portefeuille admin {identifiant_unique()}"
        )
        return Asset.objects.create(
            name="Monnaie locale admin",
            currency_code="EUR",
            category=Asset.TLF,
            tenant_origin=self.tenant,
            wallet_origin=portefeuille_d_origine,
        )

    def _operateur(self, prenom="", nom=""):
        """
        Un utilisateur qui opère la caisse (schéma public, annulé avec le test).
        / A user operating the register (rolled back with the test).
        """
        email_de_l_operateur = f"operateur-{identifiant_unique()}@tibillet.localhost"
        return TibilletUser.objects.create(
            email=email_de_l_operateur,
            username=email_de_l_operateur,
            first_name=prenom,
            last_name=nom,
        )

    def _vendre_des_jus_en_especes(self, quantite=1, operateur=None):
        """
        Une vente de caisse sur le point de vente : `quantite` jus à 3,50 € en espèces.
        La ligne est VALID, comme la caisse l'écrit (un avoir peut la reprendre).
        / A register sale at the point of sale: `quantite` juices in cash.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            operateur=operateur,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal(quantite),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 350 * quantite}],
        )
        verifier_egalites(vente)
        return vente

    def _rembourser_en_especes(self, vente):
        """
        L'avoir de la ligne d'une vente, remboursé en espèces (bouton « Avoir »).
        / The credit note of a sale's line, refunded in cash.
        """
        ligne_vendue = LigneArticle.objects.get(vente=vente)
        with taches_celery_enregistrees():
            article_d_avoir = ecrire_la_vente_d_avoir_d_une_ligne(
                ligne_vendue,
                quantite=Decimal("1"),
                moyen_rembourse=PaymentMethod.CASH,
                origine=SaleOrigin.ADMIN,
            )
        verifier_egalites(Vente.objects.get(pk=article_d_avoir.vente_id))

    def _vider_une_carte(self, montant_en_centimes):
        """
        Une carte en monnaie locale vidée à la caisse, les espèces rendues : la vente
        VIDAGE_CARTE n'a pas d'article, ses règlements s'annulent.
        / A local currency card emptied at the register, cash given back.
        """
        monnaie_locale = self._monnaie_locale()
        vente_du_vidage = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VIDAGE_CARTE,
            point_de_vente=self.point_de_vente,
            reglements=[
                {
                    "moyen": PaymentMethod.LOCAL_EURO,
                    "montant": montant_en_centimes,
                    "asset": monnaie_locale.uuid,
                },
                {"moyen": PaymentMethod.CASH, "montant": -montant_en_centimes},
            ],
        )
        verifier_egalites(vente_du_vidage)

    def _corriger_les_especes_en_cb(self, vente_d_origine, operateur):
        """
        La correction d'un jus payé en espèces : une vente CORRECTION liée, sans
        article, espèces −350 et CB +350 (D14).
        / The correction of a cash juice: cash −350, card +350.
        """
        vente_de_correction = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.CORRECTION,
            vente_liee=vente_d_origine,
            operateur=operateur,
            point_de_vente=self.point_de_vente,
        )
        ajouter_reglement(vente_de_correction, moyen=PaymentMethod.CASH, montant=-350)
        ajouter_reglement(vente_de_correction, moyen=PaymentMethod.CC, montant=350)
        vente_de_correction = encaisser_vente(vente_de_correction)
        verifier_egalites(vente_de_correction)
        return vente_de_correction

    def _cloturer_la_journee(self):
        """
        Le « Z de fin de service », une minute après les ventes du test : la J
        glissante couvre toutes les ventes faites jusque-là.
        / The end-of-service Z, one minute after the test's sales.
        """
        moment_de_la_cloture = timezone.now() + timedelta(minutes=1)
        with patch("django.utils.timezone.now", return_value=moment_de_la_cloture):
            uuid_de_la_cloture = comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            )
        return ClotureCaisse.objects.get(uuid=uuid_de_la_cloture)

    def _contexte_de_la_fiche(self, cloture):
        """
        Appelle `changeform_view` de l'admin des clôtures et rend le contexte qu'elle
        passe à la vue de Django (remplacée par un bouchon : le rendu complet d'Unfold
        plante en test).
        / Calls the admin changeform_view and returns the context it passes on.
        """
        contexte_capture = {}

        def vue_de_django_bouchonnee(
            admin, requete, object_id=None, form_url="", extra_context=None
        ):
            contexte_capture.update(extra_context)
            return HttpResponse("bouchon")

        requete = self._requete(
            f"/admin/comptabilite/cloturecaisse/{cloture.uuid}/change/"
        )
        with patch.object(
            DjangoModelAdmin, "changeform_view", vue_de_django_bouchonnee
        ):
            self.admin_des_clotures.changeform_view(requete, object_id=str(cloture.uuid))
        return contexte_capture

    def _page_des_sections(self, sections):
        """
        Le HTML des sections du rapport (gabarit partagé par la fiche et le temps réel),
        en français.
        / The HTML of the report sections, in French.
        """
        with translation.override("fr"):
            return render_to_string(
                "comptabilite/admin/_sections_rapport.html", {"sections": sections}
            )

    def _page_de_la_cloture(self, cloture):
        """La page des sections d'une clôture. / The sections page of a closure."""
        contexte_de_la_fiche = self._contexte_de_la_fiche(cloture)
        return self._page_des_sections(contexte_de_la_fiche["sections"])

    def _sections_en_francais(self, rapport):
        """Les sections d'un rapport, en français. / A report's sections, in French."""
        with translation.override("fr"):
            return sections_pour_affichage(rapport)

    def _section(self, sections, cle):
        """La section `cle` d'une liste de sections. / The section with this key."""
        for section in sections:
            if section["cle"] == cle:
                return section
        raise AssertionError(f"Section absente : {cle}")

    def _tableau(self, section, testid):
        """Le tableau `testid` d'une section. / The table with this testid."""
        for tableau in section["tableaux"]:
            if tableau["testid"] == testid:
                return tableau
        raise AssertionError(f"Tableau absent : {testid}")

    def _lignes_de_l_en_tete(self, sections):
        """
        Les lignes de l'en-tête, par libellé : {libellé: texte de la valeur}.
        / The header rows, by label.
        """
        section_en_tete = self._section(sections, "en_tete")
        tableau_de_l_en_tete = self._tableau(section_en_tete, "en-tete")
        textes_par_libelle = {}
        for ligne in tableau_de_l_en_tete["lignes"]:
            textes_par_libelle[ligne[0]["texte"]] = ligne[1]["texte"]
        return textes_par_libelle

    def _page_de_la_fiche_complete(self, cloture):
        """
        Le gabarit de la fiche d'une clôture (`change_form_before.html`), rendu en
        français avec le contexte que `changeform_view` lui passe.
        / The closure page template, rendered with the context of changeform_view.
        """
        contexte_de_la_fiche = self._contexte_de_la_fiche(cloture)
        with translation.override("fr"):
            return render_to_string(
                "comptabilite/admin/change_form_before.html", contexte_de_la_fiche
            )

    def _vendre_et_cloturer_le_10_mars(self):
        """
        Un jus vendu le 10 mars à 10 h (Paris), la J demandée à 12 h.
        / A juice sold on March 10 at 10:00 (Paris), the J at 12:00.
        """
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 3, 10, 10, 0)
        ):
            self._vendre_des_jus_en_especes()
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 3, 10, 12, 0)
        ):
            uuid_de_la_j = comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            )
        return ClotureCaisse.objects.get(uuid=uuid_de_la_j)

    def _rapport_temps_reel(self):
        """
        Appelle la vue du rapport temps réel sur la dernière heure et la prochaine, et
        rend le contexte passé au gabarit (le rendu complet d'Unfold plante en test).
        / Calls the real-time report view and returns the template context.
        """
        contexte_capture = {}

        def rendu_bouchonne(requete, nom_du_gabarit, contexte=None, *args, **kwargs):
            contexte_capture["gabarit"] = nom_du_gabarit
            contexte_capture.update(contexte)
            return HttpResponse("bouchon")

        # Les heures saisies sont en heure du lieu (Paris), comme dans le formulaire.
        # / Typed hours are in the venue's time, as in the form.
        maintenant_local = timezone.localtime(
            timezone.now(), ZoneInfo("Europe/Paris")
        )
        parametres = {
            "datetime_debut": (maintenant_local - timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "datetime_fin": (maintenant_local + timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
        }
        requete = self._requete(
            "/admin/comptabilite/cloturecaisse/rapport-temps-reel/", parametres
        )
        with patch("django.shortcuts.render", side_effect=rendu_bouchonne):
            self.admin_des_clotures.rapport_temps_reel(requete)
        return contexte_capture

    # ------------------------------------------------------------------
    # L'admin : permissions et adresses
    # / The admin: permissions and URLs
    # ------------------------------------------------------------------

    def test_app_comptabilite_dans_installed_apps(self):
        """
        L'app comptabilite est chargée par Django.
        / The comptabilite app is loaded by Django.
        """
        from django.apps import apps

        assert apps.is_installed("comptabilite")

    def test_admin_permissions_lecture_seule(self):
        """
        Une clôture est immuable : ni ajout, ni modification, ni suppression.
        / A closure is immutable: no add, change, delete.
        """
        assert self.admin_des_clotures.has_add_permission(None) is False
        assert self.admin_des_clotures.has_change_permission(None) is False
        assert self.admin_des_clotures.has_delete_permission(None) is False

    def test_admin_urls_custom_enregistrees(self):
        """
        L'admin expose le rapport temps réel et les quatre exports (CSV du rapport,
        tableur, PDF, FEC).
        / The admin exposes the real-time report and the four exports.
        """
        noms_des_adresses = set()
        adresses_de_l_admin = self.admin_des_clotures.get_urls()
        for adresse in adresses_de_l_admin:
            if adresse.name:
                noms_des_adresses.add(adresse.name)
        adresses_attendues = {
            "comptabilite_cloturecaisse_temps_reel",
            "comptabilite_cloturecaisse_csv",
            "comptabilite_cloturecaisse_excel",
            "comptabilite_cloturecaisse_pdf",
            "comptabilite_cloturecaisse_fec",
        }
        assert adresses_attendues.issubset(noms_des_adresses)

    def test_plus_d_export_csv_comptable(self):
        """
        Le seul export comptable est le FEC. La fiche d'une clôture n'a plus de bouton
        « CSV comptable » ; elle dit d'importer le FEC dans le logiciel comptable.
        L'adresse d'export CSV comptable n'existe plus : son nom ne se retrouve pas
        (`NoReverseMatch`) et aucune adresse de l'admin des clôtures ne la porte.
        L'ancienne adresse tombe sur la redirection générique de l'admin Django vers
        la fiche d'un objet, qui n'existe pas : aucun fichier n'est produit.
        / The FEC is the only accounting export: no CSV button, no CSV route.
        """
        self._vendre_des_jus_en_especes()
        cloture = self._cloturer_la_journee()

        page = self._page_de_la_fiche_complete(cloture)

        assert 'data-testid="comptabilite-export-fec"' in page
        assert "exporter-csv-comptable" not in page
        assert "CSV comptable" not in page
        assert "importez le FEC" in page

        with self.assertRaises(NoReverseMatch):
            reverse(
                "staff_admin:comptabilite_cloturecaisse_csv_comptable",
                args=[cloture.pk],
            )
        motifs_des_adresses = []
        adresses_de_l_admin = self.admin_des_clotures.get_urls()
        for adresse in adresses_de_l_admin:
            motifs_des_adresses.append(str(adresse.pattern))
        for motif in motifs_des_adresses:
            assert "csv-comptable" not in motif, motif

    # ------------------------------------------------------------------
    # Les montants à la française
    # / French amounts
    # ------------------------------------------------------------------

    def test_montant_a_la_francaise_avec_centimes_et_milliers(self):
        """
        Les centimes deviennent des euros à la française : deux décimales après une
        virgule, les milliers séparés, « € » après une espace insécable. Un négatif
        porte le signe moins typographique.
        / Cents become French euros: two decimals, thousands separated, "€" after a
        non-breaking space; a negative amount has the typographic minus.
        """
        assert euros_a_la_francaise(105000) == euros("1 050,00")
        assert euros_a_la_francaise(1050) == euros("10,50")
        assert euros_a_la_francaise(5) == euros("0,05")
        assert euros_a_la_francaise(0) == euros("0,00")
        assert euros_a_la_francaise(123456789) == euros("1 234 567,89")
        assert euros_a_la_francaise(-350) == f"{SIGNE_MOINS}{euros('3,50')}"

    # ------------------------------------------------------------------
    # La fiche d'une clôture
    # / The closure page
    # ------------------------------------------------------------------

    def test_fiche_d_une_j_sections_dans_l_ordre_de_la_fiche(self):
        """
        La fiche d'une J montre d'abord l'essentiel (en-tête, chiffre d'affaires,
        règlements, caisse espèces, réconciliation, offerts), puis, repliés dans des
        `<details>`, l'annexe, les points, la marge brute, le détail et l'intégrité.
        / A J page shows the essentials first, then folded details, in the sheet's order.
        """
        self._vendre_des_jus_en_especes()
        cloture = self._cloturer_la_journee()

        page = self._page_de_la_cloture(cloture)

        positions_des_sections = []
        for cle in SECTIONS_ESSENTIELLES_D_UNE_J + SECTIONS_REPLIEES_D_UNE_J:
            marqueur = f'data-testid="comptabilite-section-{cle}"'
            assert marqueur in page, f"Section absente : {cle}"
            positions_des_sections.append(page.index(marqueur))
        assert positions_des_sections == sorted(positions_des_sections)

        for cle in SECTIONS_ESSENTIELLES_D_UNE_J:
            motif_d_une_section_ouverte = (
                rf'<section[^>]*data-testid="comptabilite-section-{cle}"'
            )
            assert re.search(motif_d_une_section_ouverte, page), cle
        for cle in SECTIONS_REPLIEES_D_UNE_J:
            motif_d_une_section_repliee = (
                rf'<details[^>]*data-testid="comptabilite-section-{cle}"'
            )
            assert re.search(motif_d_une_section_repliee, page), cle

    def test_fiche_d_une_j_montre_le_chiffre_d_affaires_en_euros(self):
        """
        Deux jus en espèces (7,00 €) : la fiche montre le chiffre d'affaires TTC à la
        française, et le contexte porte la clôture.
        / Two juices in cash: the page shows the revenue in French euros.
        """
        self._vendre_des_jus_en_especes(quantite=2)
        cloture = self._cloturer_la_journee()

        contexte_de_la_fiche = self._contexte_de_la_fiche(cloture)
        page = self._page_des_sections(contexte_de_la_fiche["sections"])

        assert contexte_de_la_fiche["cloture"] == cloture
        assert euros("7,00") in page

    def test_section_caisse_especes_absente_d_une_m(self):
        """
        Une clôture mensuelle n'a pas de caisse espèces (un fond de caisse n'a de sens
        que pour une journée) : sa fiche n'a pas cette section. Deux jus vendus en
        février, la M de février créée le 2 mars.
        / A monthly closure has no cash drawer section.
        """
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 2, 10, 18, 0)
        ):
            self._vendre_des_jus_en_especes(quantite=2)
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 3, 2, 10, 0)
        ):
            uuid_de_la_m = comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_MENSUEL,
            )
        cloture_mensuelle = ClotureCaisse.objects.get(uuid=uuid_de_la_m)

        page = self._page_de_la_cloture(cloture_mensuelle)

        assert 'data-testid="comptabilite-section-chiffre-affaires"' in page
        assert 'data-testid="comptabilite-section-caisse-especes"' not in page

    def test_phrase_de_reconciliation_montants_positifs_avec_moins(self):
        """
        La phrase de réconciliation, écrite par l'affichage, sur une J mêlée :
        - deux jus en espèces (7,00 €) et un jus en espèces (3,50 €) remboursé en
          espèces par un avoir (−3,50 €) ;
        - une carte de 2,00 € vidée, les espèces rendues (−2,00 €).
        Ventes payées en argent : 700 + 350 = 1050 ; recharges 0 ; remboursements
        −350 ; cartes vidées −200 ; écarts 0 ; argent reçu 1050 − 350 − 200 = 500.
        Les sorties s'écrivent en POSITIF après « − ».
        / The reconciliation sentence: positive amounts after "−".
        """
        self._vendre_des_jus_en_especes(quantite=2)
        vente_remboursee = self._vendre_des_jus_en_especes()
        self._rembourser_en_especes(vente_remboursee)
        self._vider_une_carte(200)
        cloture = self._cloturer_la_journee()

        sections = self._sections_en_francais(cloture.rapport_json)
        phrase = self._section(sections, "reconciliation")["phrase"]

        phrase_attendue = (
            f"Argent reçu {euros('5,00')} = ventes payées en argent {euros('10,50')} "
            f"+ recharges {euros('0,00')} − remboursements {euros('3,50')} "
            f"− cartes vidées {euros('2,00')} + écarts d'encaissement {euros('0,00')}"
        )
        assert phrase == phrase_attendue
        assert SIGNE_MOINS + "3,50" not in phrase
        assert SIGNE_MOINS + "2,00" not in phrase

        page = self._page_des_sections(sections)
        assert phrase_attendue.replace("'", "&#x27;") in page

    def test_operateur_d_une_correction_affiche_par_son_nom(self):
        """
        Le Z stocke l'identifiant de l'opérateur d'une correction, jamais son email ;
        la fiche montre son nom complet, jamais son identifiant.
        / The Z stores the operator's id; the page shows the full name, never the id.
        """
        operateur = self._operateur(prenom="Camille", nom="Dupont")
        vente_d_origine = self._vendre_des_jus_en_especes()
        self._corriger_les_especes_en_cb(vente_d_origine, operateur)
        cloture = self._cloturer_la_journee()

        correction_stockee = cloture.rapport_json["annexe"]["corrections"]["liste"][0]
        assert correction_stockee["operateur"] == str(operateur.pk)

        page = self._page_de_la_cloture(cloture)

        assert "Camille Dupont" in page
        assert str(operateur.pk) not in page

    def test_operateur_sans_nom_affiche_par_son_email(self):
        """
        Un opérateur sans prénom ni nom s'affiche par son email.
        / An operator without a name is shown by email.
        """
        operateur = self._operateur()
        vente_d_origine = self._vendre_des_jus_en_especes()
        self._corriger_les_especes_en_cb(vente_d_origine, operateur)
        cloture = self._cloturer_la_journee()

        page = self._page_de_la_cloture(cloture)

        assert operateur.email in page

    def test_operateur_disparu_affiche_compte_supprime(self):
        """
        Un identifiant d'opérateur qui ne correspond plus à aucun compte s'affiche
        « Compte supprimé » (avec une majuscule, comme « Sans opérateur »). Le rapport
        stocké n'est jamais réécrit : on lit une copie du rapport dont l'identifiant ne
        correspond à personne.
        / An operator id with no account is shown as "Compte supprimé".
        """
        operateur = self._operateur(prenom="Camille", nom="Dupont")
        vente_d_origine = self._vendre_des_jus_en_especes()
        self._corriger_les_especes_en_cb(vente_d_origine, operateur)
        cloture = self._cloturer_la_journee()

        rapport_avec_un_compte_disparu = copy.deepcopy(cloture.rapport_json)
        identifiant_sans_compte = str(uuid.uuid4())
        correction = rapport_avec_un_compte_disparu["annexe"]["corrections"]["liste"][0]
        correction["operateur"] = identifiant_sans_compte

        page = self._page_des_sections(
            self._sections_en_francais(rapport_avec_un_compte_disparu)
        )

        assert "Compte supprimé" in page
        assert identifiant_sans_compte not in page

    def test_integrite_ok(self):
        """
        Une J dont la chaîne des ventes est intacte : l'intégrité dit « OK ».
        / A J with an intact sales chain: integrity says "OK".
        """
        self._vendre_des_jus_en_especes()
        cloture = self._cloturer_la_journee()

        sections = self._sections_en_francais(cloture.rapport_json)
        integrite = self._section(sections, "integrite")

        assert integrite["phrase"] == "OK"
        assert integrite["tableaux"] == []

    def test_integrite_liste_les_anomalies(self):
        """
        Des anomalies dans la section intégrité : la fiche les liste (numéro de vente,
        raison). Le rapport stocké n'est pas réécrit : on lit une copie.
        / Integrity anomalies are listed (sale number, reason).
        """
        self._vendre_des_jus_en_especes()
        cloture = self._cloturer_la_journee()

        rapport_avec_une_anomalie = copy.deepcopy(cloture.rapport_json)
        rapport_avec_une_anomalie["integrite"] = {
            "statut": "ANOMALIES",
            "anomalies": [
                {
                    "numero": 4242,
                    "uuid": str(uuid.uuid4()),
                    "raison": "Empreinte différente : vente modifiée après coup.",
                },
            ],
        }

        page = self._page_des_sections(
            self._sections_en_francais(rapport_avec_une_anomalie)
        )

        assert "4242" in page
        assert "Empreinte différente : vente modifiée après coup." in page
        assert 'data-testid="comptabilite-integrite-anomalies"' in page

    def test_ecart_d_encaissement_en_alerte_porte_un_texte(self):
        """
        Le tableau des écarts d'encaissement en alerte n'est pas seulement rouge : il
        porte le texte « Attention : écart d'encaissement » (une couleur seule ne se lit
        pas avec un lecteur d'écran). Le rapport stocké n'est pas réécrit : on lit une
        copie avec un écart.
        / The gap table in alert also carries a text, not only a color.
        """
        self._vendre_des_jus_en_especes()
        cloture = self._cloturer_la_journee()

        page_sans_ecart = self._page_des_sections(
            self._sections_en_francais(cloture.rapport_json)
        )
        rapport_avec_un_ecart = copy.deepcopy(cloture.rapport_json)
        rapport_avec_un_ecart["annexe"]["ecarts_d_encaissement"] = {
            "nombre": 1,
            "total_en_centimes": 3,
        }
        page_avec_un_ecart = self._page_des_sections(
            self._sections_en_francais(rapport_avec_un_ecart)
        )

        texte_d_alerte = "Attention : écart d&#x27;encaissement"
        assert texte_d_alerte in page_avec_un_ecart
        assert texte_d_alerte not in page_sans_ecart

    def test_jetons_cadeau_repris_ecrits_tels_quels(self):
        """
        Les jetons cadeau repris au vidage sont positifs par construction : l'annexe
        les écrit tels quels, sans effacer un signe inattendu. Une copie du rapport
        porte −5,00 € de jetons repris : la fiche écrit « −5,00 € ».
        / Gift tokens taken back are written as is: an unexpected sign stays visible.
        """
        self._vendre_des_jus_en_especes()
        cloture = self._cloturer_la_journee()
        rapport_avec_un_signe_inattendu = copy.deepcopy(cloture.rapport_json)
        cartes_videes = rapport_avec_un_signe_inattendu["annexe"]["recharges_et_cartes"][
            "cartes_videes"
        ]
        cartes_videes["jetons_cadeau_repris_en_centimes"] = -500

        sections = self._sections_en_francais(rapport_avec_un_signe_inattendu)
        tableau_des_recharges = self._tableau(
            self._section(sections, "annexe"), "annexe-recharges-et-cartes"
        )
        textes_par_libelle = {}
        for ligne in tableau_des_recharges["lignes"]:
            textes_par_libelle[ligne[0]["texte"]] = ligne[2]["texte"]

        assert textes_par_libelle["dont jetons cadeau repris"] == (
            f"{SIGNE_MOINS}{euros('5,00')}"
        )

    # ------------------------------------------------------------------
    # Le gabarit de la fiche, rendu pour de vrai
    # / The closure page template, really rendered
    # ------------------------------------------------------------------

    def test_gabarit_de_la_fiche_d_une_j_rendu_avec_le_contexte_de_l_admin(self):
        """
        Le gabarit de la fiche (`change_form_before.html`), rendu avec le contexte que
        `changeform_view` lui passe, sur une J d'un jus en espèces : le bandeau des
        exports, l'empreinte de la clôture, toutes les sections d'une J, les mentions
        légales et la phrase de réconciliation. Une variable renommée dans la vue ou
        dans le gabarit fait tomber ce test.
        / The closure page template, rendered with the admin context: exports, the
        closure fingerprint, every J section, legal mentions, reconciliation sentence.
        """
        self._vendre_des_jus_en_especes()
        cloture = self._cloturer_la_journee()

        page = self._page_de_la_fiche_complete(cloture)

        assert 'data-testid="comptabilite-bandeau-exports"' in page
        assert cloture.hmac_hash in page
        for cle in SECTIONS_ESSENTIELLES_D_UNE_J + SECTIONS_REPLIEES_D_UNE_J:
            assert f'data-testid="comptabilite-section-{cle}"' in page, cle
        assert "Ville du lieu de test" in page
        assert "Opérations numérotées" in page
        # Un jus en espèces : 3,50 € reçus = 3,50 € de ventes payées en argent.
        # / One cash juice: 3.50 received = 3.50 of sales paid in money.
        phrase_attendue = (
            f"Argent reçu {euros('3,50')} = ventes payées en argent {euros('3,50')} "
            f"+ recharges {euros('0,00')} − remboursements {euros('0,00')} "
            f"− cartes vidées {euros('0,00')} + écarts d'encaissement {euros('0,00')}"
        )
        assert phrase_attendue.replace("'", "&#x27;") in page

    def test_gabarit_de_la_fiche_d_une_m_rendu_avec_le_contexte_de_l_admin(self):
        """
        Le gabarit de la fiche, rendu avec le contexte de `changeform_view`, sur la M de
        février (deux jus vendus le 10, M créée le 2 mars) : l'empreinte, l'en-tête et
        le chiffre d'affaires (7,00 €), jamais la caisse espèces ni l'intégrité.
        / The page template of an M: fingerprint, header, revenue; no cash drawer nor
        integrity.
        """
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 2, 10, 18, 0)
        ):
            self._vendre_des_jus_en_especes(quantite=2)
        with patch(
            "django.utils.timezone.now", return_value=heure_de_paris(2026, 3, 2, 10, 0)
        ):
            uuid_de_la_m = comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_MENSUEL,
            )
        cloture_mensuelle = ClotureCaisse.objects.get(uuid=uuid_de_la_m)

        page = self._page_de_la_fiche_complete(cloture_mensuelle)

        assert cloture_mensuelle.hmac_hash in page
        assert 'data-testid="comptabilite-section-en-tete"' in page
        assert 'data-testid="comptabilite-section-chiffre-affaires"' in page
        assert euros("7,00") in page
        assert 'data-testid="comptabilite-section-caisse-especes"' not in page
        assert 'data-testid="comptabilite-section-integrite"' not in page

    # ------------------------------------------------------------------
    # Les libellés de l'en-tête et des règlements
    # / Header and payment labels
    # ------------------------------------------------------------------

    def test_en_tete_compte_les_operations_numerotees_dont_avoirs_vidages_corrections(
        self,
    ):
        """
        L'en-tête compte les opérations numérotées (toutes les ventes réglées, quelle
        que soit leur nature), et dit combien sont des avoirs, des cartes vidées et des
        corrections. Trois nombres différents, pour qu'une ligne ne puisse pas lire le
        nombre d'une autre : une vente de deux jus ; une vente d'un jus et son avoir ;
        deux cartes vidées ; trois ventes d'un jus, chacune corrigée. Opérations :
        1 + 2 + 2 + 3 × 2 = 11, dont 1 avoir, 2 cartes vidées, 3 corrections. Le libellé
        « Nombre de ventes » n'existe plus.
        / The header counts numbered operations, with credit notes, emptied cards and
        corrections.
        """
        self._vendre_des_jus_en_especes(quantite=2)
        vente_remboursee = self._vendre_des_jus_en_especes()
        self._rembourser_en_especes(vente_remboursee)
        self._vider_une_carte(200)
        self._vider_une_carte(300)
        operateur = self._operateur(prenom="Camille", nom="Dupont")
        for _numero_de_la_correction in range(3):
            vente_corrigee = self._vendre_des_jus_en_especes()
            self._corriger_les_especes_en_cb(vente_corrigee, operateur)
        cloture = self._cloturer_la_journee()

        lignes_de_l_en_tete = self._lignes_de_l_en_tete(
            self._sections_en_francais(cloture.rapport_json)
        )

        assert lignes_de_l_en_tete["Opérations numérotées"] == "11"
        assert lignes_de_l_en_tete["dont avoirs"] == "1"
        assert lignes_de_l_en_tete["dont cartes vidées"] == "2"
        assert lignes_de_l_en_tete["dont corrections"] == "3"
        assert "Nombre de ventes" not in lignes_de_l_en_tete

    def test_offert_des_reglements_dit_bouton_offrir_et_cadeaux_emis(self):
        """
        Le bloc « hors argent » des règlements nomme son offert « Offert (bouton
        OFFRIR et cadeaux émis) » : il additionne les règlements offerts, recharge
        cadeau comprise, alors que la section « Offerts » ne compte que le bouton
        OFFRIR.
        / The payments' off-money "offered" line names what it adds up.
        """
        self._vendre_des_jus_en_especes()
        cloture = self._cloturer_la_journee()

        sections = self._sections_en_francais(cloture.rapport_json)
        tableau_hors_argent = self._tableau(
            self._section(sections, "reglements"), "reglements-hors-argent"
        )

        assert (
            tableau_hors_argent["lignes"][0][0]["texte"]
            == "Offert (bouton OFFRIR et cadeaux émis)"
        )

    # ------------------------------------------------------------------
    # Les mentions légales, figées dans le Z
    # / Legal mentions, frozen in the Z
    # ------------------------------------------------------------------

    def test_mentions_legales_affichees_et_figees_dans_le_z(self):
        """
        Les mentions légales du lieu sont figées dans le Z à la clôture : un ancien Z
        garde l'ancienne adresse. La fiche les affiche ; un changement d'adresse ou de
        SIREN APRÈS la clôture ne change pas le Z affiché (relu depuis la base).
        / Legal mentions are stored in the Z; changing them afterwards does not change
        the displayed Z.
        """
        configuration = Configuration.get_solo()
        configuration.city = "Ville avant la clôture"
        configuration.siren = "111222333"
        configuration.save()
        self._vendre_des_jus_en_especes()
        cloture = self._cloturer_la_journee()

        configuration = Configuration.get_solo()
        configuration.city = "Ville après la clôture"
        configuration.siren = "999888777"
        configuration.save()
        cloture_relue = ClotureCaisse.objects.get(pk=cloture.pk)

        page = self._page_de_la_cloture(cloture_relue)

        assert "Ville avant la clôture" in page
        assert "111222333" in page
        assert "Ville après la clôture" not in page
        assert "999888777" not in page

    def test_fiche_d_un_z_sans_mentions_legales_ne_plante_pas(self):
        """
        Un Z stocké sans mentions légales (une ancienne clôture) s'affiche : chaque
        mention vaut « — ». Le rapport stocké n'est pas réécrit : on lit une copie.
        / A stored Z without legal mentions is displayed, each mention as "—".
        """
        self._vendre_des_jus_en_especes()
        cloture = self._cloturer_la_journee()
        rapport_sans_mentions_legales = copy.deepcopy(cloture.rapport_json)
        del rapport_sans_mentions_legales["en_tete"]["mentions_legales"]

        lignes_de_l_en_tete = self._lignes_de_l_en_tete(
            self._sections_en_francais(rapport_sans_mentions_legales)
        )

        assert lignes_de_l_en_tete["Ville"] == "—"
        assert lignes_de_l_en_tete["SIREN / SIRET"] == "—"

    # ------------------------------------------------------------------
    # Le fuseau horaire, figé dans le Z
    # / The time zone, frozen in the Z
    # ------------------------------------------------------------------

    def test_z_garde_le_fuseau_de_sa_cloture_quand_le_lieu_change_de_fuseau(self):
        """
        Une J le 10 mars de 10 h à 12 h, à Paris (UTC+1). Le lieu passe ensuite en
        Martinique (UTC−4). Le Z stocke le fuseau du calcul (« Europe/Paris ») et
        s'affiche toujours dans ce fuseau : début 10:00, fin 12:00 (et non 05:00 et
        07:00, les mêmes instants à la Martinique).
        / A Z keeps the time zone of its closure when the venue changes zone.
        """
        cloture = self._vendre_et_cloturer_le_10_mars()
        assert cloture.rapport_json["en_tete"]["fuseau_horaire"] == "Europe/Paris"

        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "America/Martinique"
        configuration.save()
        cloture_relue = ClotureCaisse.objects.get(pk=cloture.pk)

        lignes_de_l_en_tete = self._lignes_de_l_en_tete(
            self._sections_en_francais(cloture_relue.rapport_json)
        )

        assert lignes_de_l_en_tete["Fin"] == "10/03/2026 12:00"
        heure_de_la_vente = Vente.objects.get().datetime_encaissement
        debut_attendu = heure_de_la_vente.astimezone(FUSEAU_DE_PARIS).strftime(
            "%d/%m/%Y %H:%M"
        )
        assert lignes_de_l_en_tete["Début"] == debut_attendu

    def test_z_sans_fuseau_fige_s_affiche_dans_le_fuseau_actuel_du_lieu(self):
        """
        Un Z stocké sans fuseau (une ancienne clôture) s'affiche dans le fuseau actuel
        du lieu : la J finie le 10 mars à 12 h à Paris (11 h UTC) s'affiche 07:00 dans un
        lieu passé en Martinique (UTC−4). On lit une copie du rapport stocké.
        / A Z stored without a time zone is displayed in the venue's current zone.
        """
        cloture = self._vendre_et_cloturer_le_10_mars()
        rapport_sans_fuseau = copy.deepcopy(cloture.rapport_json)
        rapport_sans_fuseau["en_tete"].pop("fuseau_horaire", None)

        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "America/Martinique"
        configuration.save()

        lignes_de_l_en_tete = self._lignes_de_l_en_tete(
            self._sections_en_francais(rapport_sans_fuseau)
        )

        assert lignes_de_l_en_tete["Fin"] == "10/03/2026 07:00"

    # ------------------------------------------------------------------
    # Le rapport temps réel
    # / The real-time report
    # ------------------------------------------------------------------

    def _contexte_du_rapport_temps_reel(self, parametres=None):
        """
        Appelle la vue du rapport temps réel avec ces paramètres, et rend le contexte
        passé au gabarit.
        / Calls the real-time report view and returns the template context.
        """
        contexte_capture = {}

        def rendu_bouchonne(requete, nom_du_gabarit, contexte=None, *args, **kwargs):
            contexte_capture.update(contexte)
            return HttpResponse("bouchon")

        requete = self._requete(
            "/admin/comptabilite/cloturecaisse/rapport-temps-reel/", parametres
        )
        with patch("django.shortcuts.render", side_effect=rendu_bouchonne):
            self.admin_des_clotures.rapport_temps_reel(requete)
        return contexte_capture

    def test_rapport_temps_reel_bornes_par_defaut_depuis_la_derniere_j(self):
        """
        Sans paramètre, le rapport temps réel montre le service en cours : depuis la
        fin de la dernière J (le 10 mars à 12 h, Paris) jusqu'à maintenant.
        / Default bounds: from the end of the last J to now.
        """
        vente_a_10h = datetime(2026, 3, 10, 10, 0, tzinfo=ZoneInfo("Europe/Paris"))
        fin_de_la_j = datetime(2026, 3, 10, 12, 0, tzinfo=ZoneInfo("Europe/Paris"))
        with patch("django.utils.timezone.now", return_value=vente_a_10h):
            self._vendre_des_jus_en_especes()
        with patch("django.utils.timezone.now", return_value=fin_de_la_j):
            comptabilite.tasks.generer_cloture_pour_tenant(
                schema_name=self.tenant.schema_name,
                niveau=ClotureCaisse.NIVEAU_JOURNALIER,
            )

        contexte_capture = self._contexte_du_rapport_temps_reel()

        assert contexte_capture["datetime_debut"] == fin_de_la_j
        ecart_avec_maintenant = timezone.now() - contexte_capture["datetime_fin"]
        assert ecart_avec_maintenant.total_seconds() < 5

    def test_rapport_temps_reel_sans_j_commence_a_la_premiere_vente(self):
        """
        Aucune J : le rapport temps réel commence à la première vente du lieu (le 10
        mars à 10 h, Paris).
        / Without any J, the default start is the venue's first sale.
        """
        vente_a_10h = datetime(2026, 3, 10, 10, 0, tzinfo=ZoneInfo("Europe/Paris"))
        with patch("django.utils.timezone.now", return_value=vente_a_10h):
            self._vendre_des_jus_en_especes()

        contexte_capture = self._contexte_du_rapport_temps_reel()

        assert contexte_capture["datetime_debut"] == vente_a_10h

    def test_rapport_temps_reel_heures_du_lieu(self):
        """
        Lieu en Martinique (UTC−4) : « 2026-05-14T10:00 » saisi est 10 h à la
        Martinique (14 h UTC), quel que soit le fuseau du serveur ; il est réaffiché
        « 2026-05-14T10:00 » et « 14/05/2026 10:00 ».
        / Typed and displayed hours are in the venue's time zone.
        """
        configuration = Configuration.get_solo()
        configuration.fuseau_horaire = "America/Martinique"
        configuration.save()

        contexte_capture = self._contexte_du_rapport_temps_reel(
            {"datetime_debut": "2026-05-14T10:00", "datetime_fin": "2026-05-14T18:00"}
        )

        assert contexte_capture["datetime_debut"] == datetime(
            2026, 5, 14, 14, 0, tzinfo=ZoneInfo("UTC")
        )
        assert contexte_capture["datetime_debut_input"] == "2026-05-14T10:00"
        assert contexte_capture["datetime_debut_affiche"] == "14/05/2026 10:00"
        assert contexte_capture["datetime_fin_affiche"] == "14/05/2026 18:00"

    def test_rapport_temps_reel_bornes_choisies_et_inversees(self):
        """
        Les bornes choisies sont relues ; un début après la fin est inversé.
        / Chosen bounds are read back; a start after the end is swapped.
        """
        contexte_capture = {}

        def rendu_bouchonne(requete, nom_du_gabarit, contexte=None, *args, **kwargs):
            contexte_capture.update(contexte)
            return HttpResponse("bouchon")

        requete = self._requete(
            "/admin/comptabilite/cloturecaisse/rapport-temps-reel/",
            {"datetime_debut": "2026-05-14T18:00", "datetime_fin": "2026-05-14T10:00"},
        )
        with patch("django.shortcuts.render", side_effect=rendu_bouchonne):
            self.admin_des_clotures.rapport_temps_reel(requete)

        assert contexte_capture["datetime_debut_input"] == "2026-05-14T10:00"
        assert contexte_capture["datetime_fin_input"] == "2026-05-14T18:00"

    def test_rapport_temps_reel_lit_le_moteur_unique(self):
        """
        Le rapport temps réel est le rapport X du moteur unique : un jus en espèces
        donne un chiffre d'affaires TTC de 350 dans la section « chiffre_affaires ».
        / The real-time report is the single engine's X report.
        """
        self._vendre_des_jus_en_especes()

        contexte = self._rapport_temps_reel()

        assert contexte["gabarit"] == "comptabilite/views/rapport_temps_reel.html"
        assert contexte["rapport"]["chiffre_affaires"]["total_ttc_en_centimes"] == 350
        assert contexte["rapport"]["en_tete"]["nombre_de_ventes"] == 1

    def test_rapport_temps_reel_montre_habitus_et_operateurs_sans_integrite(self):
        """
        Le rapport X montre l'habitus des cartes et les opérateurs (l'email est permis :
        rien n'est stocké), jamais l'intégrité (un contrôle du Z, trop lourd).
        / The X report shows card habits and operators, never integrity.
        """
        operateur = self._operateur()
        self._vendre_des_jus_en_especes(operateur=operateur)

        contexte = self._rapport_temps_reel()
        page = self._page_des_sections(contexte["sections"])

        assert "integrite" not in contexte["rapport"]
        assert 'data-testid="comptabilite-section-habitus-cartes"' in page
        assert 'data-testid="comptabilite-section-operateurs"' in page
        assert 'data-testid="comptabilite-section-integrite"' not in page
        assert operateur.email in page

    def test_gabarit_du_rapport_temps_reel_rendu_par_la_vue(self):
        """
        La vue du rapport temps réel rend VRAIMENT son gabarit
        (`rapport_temps_reel.html`, aucun bouchon) sur la dernière heure et la
        prochaine, en heure de Paris, avec un jus vendu : les heures saisies dans le
        formulaire, la phrase de la période, le nombre de ventes (1), les sections du
        rapport X (habitus des cartes, opérateurs), jamais l'intégrité. Une variable
        renommée dans la vue ou dans le gabarit fait tomber ce test.
        / The real-time report view really renders its template.
        """
        self._vendre_des_jus_en_especes()
        maintenant_local = timezone.localtime(timezone.now(), FUSEAU_DE_PARIS)
        debut_local = maintenant_local - timedelta(hours=1)
        fin_local = maintenant_local + timedelta(hours=1)
        parametres = {
            "datetime_debut": debut_local.strftime("%Y-%m-%dT%H:%M"),
            "datetime_fin": fin_local.strftime("%Y-%m-%dT%H:%M"),
        }
        requete = self._requete(
            "/admin/comptabilite/cloturecaisse/rapport-temps-reel/", parametres
        )

        with translation.override("fr"):
            reponse = self.admin_des_clotures.rapport_temps_reel(requete)
        page = reponse.content.decode("utf-8")

        assert reponse.status_code == 200
        assert f'value="{parametres["datetime_debut"]}"' in page
        assert f'value="{parametres["datetime_fin"]}"' in page
        phrase_de_la_periode = (
            f"Période sélectionnée : du {debut_local:%d/%m/%Y %H:%M} "
            f"au {fin_local:%d/%m/%Y %H:%M}."
        )
        assert phrase_de_la_periode in page
        assert '<span data-testid="comptabilite-nombre-de-ventes">1</span>' in page
        assert 'data-testid="comptabilite-section-chiffre-affaires"' in page
        assert 'data-testid="comptabilite-section-habitus-cartes"' in page
        assert 'data-testid="comptabilite-section-operateurs"' in page
        assert 'data-testid="comptabilite-section-integrite"' not in page
