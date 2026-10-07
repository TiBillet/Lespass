"""
La bascule en un clic : un lieu legacy passe au moteur V2 en allumant un module V2,
si rien ne le retient sur l'ancien Fedow.
/ One-click switch: a legacy venue moves to the V2 engine by switching on a V2 module,
when nothing keeps it on the old Fedow.

LOCALISATION : tests/pytest/test_bascule_vers_v2.py

RÈGLE MÉTIER TESTÉE
Spec : TECH_DOC/SESSIONS/FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md §2 décision 6, §5.8
(et §5.1, §5.2 qu'elle modifie), brief TECH_DOC/SESSIONS/FEDOW_IMPORT/briefs/15-5.md.
- `raisons_qui_empechent_le_passage_en_v2(lieu)` rend une liste de phrases, vide quand le
  lieu peut passer en V2. Sept raisons, dans cet ordre, une phrase par raison présente :
  1. le lieu est l'agenda partagé (`Client.META`) ;
  2. le lieu a un serveur LaBoutik V1 (`Configuration.server_cashless` renseigné) ;
  3. le lieu accepte la monnaie legacy d'un autre lieu (`federated_with`, archivées
     comprises, hors `FED`, `SUB` et `BDG`) ;
  4. le lieu est invité sur une monnaie legacy (`pending_invitations`, archivées
     comprises, hors `FED`, `SUB` et `BDG`) ;
  5. le lieu a créé une monnaie legacy autre qu'adhésion (`SUB`) ou badge (`BDG`),
     archivées comprises ;
  6. des cartes NFC ont le lieu pour origine (`Detail.origine`) ;
  7. un paiement Stripe du lieu est relié à une transaction Fedow et a au moins une
     ligne d'un produit autre qu'une adhésion, ou aucune ligne, quel que soit son statut.
  Ne retiennent pas : les adhésions envoyées à Fedow (`Membership.fedow_transactions`), une
  `FedowTransaction` seule.
- `module_toggle` : un lieu legacy qui ALLUME un module V2 (caisse, monnaie locale, kiosk,
  tireuse)
  - avec une raison : refus comme avant (aucune écriture, `HX-Refresh`), le message dit
    « pas encore disponible », cite les raisons et la phrase de fin (« Contactez l'équipe TiBillet… ») ; le moteur reste
    legacy ;
  - sans raison : le moteur passe à v2 en base (et sur `connection.tenant`), puis la suite
    habituelle (la caisse allume la monnaie locale), le tout dans une seule transaction :
    une erreur de l'enregistrement annule aussi la bascule (base et `connection.tenant`).
    Un `logger.info` le note.
  Éteindre un module : inchangé, jamais de bascule. Allumer un module qui n'est pas V2 :
  jamais de bascule. Un lieu v2 : inchangé, il ne repasse jamais legacy.
- Fenêtre de confirmation (`module_toggle_modal`), lieu legacy, module V2 à allumer :
  sans raison, le texte de la bascule et le bouton de confirmation ; avec raisons, les
  raisons et la phrase de fin (« Contactez l'équipe TiBillet… »), sans bouton de confirmation.
- Carte du tableau de bord d'un module V2, lieu legacy : sans raison, la carte d'un lieu
  v2, sauf le lien d'ouverture (« Open POS », « Open kiosk ») d'un module resté allumé,
  absent tant que le lieu est legacy ; avec raisons, la carte reste fermée (`moteur_legacy`), sans
  interrupteur, et montre les raisons à la place de la phrase fixe du verrou.
- (15-5-bis) La transaction n'entoure l'enregistrement QUE pendant une bascule : sans
  bascule, l'échec du SEPA garde l'enregistrement partiel de la méthode. Après l'échec
  d'une bascule, `get_solo()` relit la base (le cache du singleton ne garde pas l'objet
  annulé). Toute autre erreur remet `connection.tenant` à legacy puis remonte. Un double
  clic ne fait qu'une bascule et un seul journal ; le bouton de confirmation se désactive
  au clic. La fenêtre est une boîte de dialogue accessible ; avec des raisons, un seul
  bouton « Fermer ». La carte retenue montre l'introduction, les raisons et la phrase de
  fin.
/ Business rules: the seven reasons, the switch inside module_toggle (one transaction),
the confirmation window, the dashboard card; 15-5-bis review fixes.

CONTRAT SUPPOSÉ (ce que ces tests attendent du code)
- `Customers/bascule_vers_v2.py` : fonction `raisons_qui_empechent_le_passage_en_v2(lieu)`.
  Elle reçoit un `Client`. Ces tests l'appellent dans le contexte de ce lieu
  (`connection.tenant` = le lieu), comme `module_toggle` et le tableau de bord. Elle rend
  des chaînes traduisibles : les tests les lisent par `str()` en français.
- Les phrases sont celles du tableau §5.8, mot pour mot (msgid français).
- `ConfigurationAdmin.module_toggle(request, field_name)` et
  `ConfigurationAdmin.module_toggle_modal(request, field_name)` gardent leur signature ;
  `module_toggle` lit la `Configuration` par `Configuration.get_solo()` et l'enregistre par
  `configuration.save()`, comme aujourd'hui. Un refus pose un message de niveau ERROR.
- Le journal de la bascule passe par le logger `Administration.admin_tenant` ; sa ligne
  contient « Bascule en un clic ».
- La fenêtre de confirmation : conteneur `role="dialog"` ; bouton de confirmation repéré
  par son `hx-post` vers `configuration-module-toggle`.
- `Administration.admin.dashboard.dashboard_callback(request, context)` rend toujours les
  cartes dans `context["groupes_de_domaines"][...]["cartes"]` ; une carte porte tout ce que
  son gabarit `admin/partials/dashboard_module_card.html` affiche, raisons comprises.
/ Assumed contract: module path and function name, unchanged admin method signatures,
logger name, cards carrying their reasons.

SIMULATIONS
- Lieu dédié `test_verrou_moteur_legacy` (`FastTenantTestCase`, schéma cloné, partagé avec
  test_verrou_moteur_legacy.py). Chaque test tourne dans une transaction annulée à la fin.
  Jamais `lespass` ni un lieu de démo. Aucun `Client` créé.
- Le moteur et la catégorie du lieu sont posés par `update()`, puis la connexion reçoit le
  `Client` relu en base (comme le middleware à chaque requête).
- La `Configuration` de la base n'est modifiée que par `update()` / `bulk_create()`, et son
  cache est vidé avant et après chaque test (tests/PIEGES.md 9.86, 13.5, 13.22). Pour
  `module_toggle`, la fenêtre et le tableau de bord, `get_solo()` rend un objet EN MÉMOIRE
  et `save()` est un faux.
- Les monnaies legacy (`AssetFedowPublic`), les cartes (`Detail`) et les portefeuilles
  sont dans le schéma public : créés dans la transaction du test (ou un point de
  sauvegarde annulé), jamais supprimés à la main (tests/PIEGES.md 13.24). L'« autre lieu »
  d'une monnaie est la ligne `Client` du schéma public, jamais un lieu de démo.
- Les produits d'une ligne de vente sont créés en catégorie « aucune », puis leur catégorie
  est posée par `update()` : le signal d'un produit d'adhésion appellerait Fedow.
/ Dedicated venue, rolled back; update()-only writes; in-memory Configuration for the
admin; public-schema objects never deleted by hand; no Fedow call.

Lancer / Run : make test ARGS="tests/pytest/test_bascule_vers_v2.py"
"""

import contextlib
import importlib
import re
import uuid
from decimal import Decimal
from html import unescape as html_unescape
from unittest.mock import patch

from django.contrib import messages as messages_django
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone, translation
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.utils import get_public_schema_name

from Administration.admin import dashboard
from Administration.admin_tenant import staff_admin_site
from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import (
    Configuration,
    FedowTransaction,
    LigneArticle,
    Membership,
    Paiement_stripe,
    Product,
    ProductSold,
)
from Customers.models import MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY, Client
from fabriques_vente import creer_tarif_vendu
from fedow_public.models import AssetFedowPublic
from QrcodeCashless.models import Detail

# Les deux valeurs du moteur (spec §3). / The two engine values.
MOTEUR_LEGACY = "legacy"
MOTEUR_V2 = "v2"

# Les modules qui utilisent le moteur V2 (spec §5.1). / The V2-engine modules.
MODULES_V2 = [
    "module_caisse",
    "module_monnaie_locale",
    "module_kiosk",
    "module_tireuse",
]

# Les sept phrases du tableau §5.8, dans l'ordre, écrites ici et jamais importées du code :
# une phrase changée dans le code doit se voir.
# / The seven sentences of the §5.8 table, in order, written here (never imported).
RAISON_1_AGENDA_PARTAGE = "Ce lieu est l'agenda partagé de TiBillet."
RAISON_2_LABOUTIK_V1 = "Votre lieu utilise LaBoutik V1."
RAISON_3_MONNAIE_D_UN_AUTRE_LIEU = (
    "Votre lieu accepte une monnaie partagée avec d'autres lieux."
)
RAISON_4_INVITATION = "Votre lieu est invité à partager une monnaie."
RAISON_5_MONNAIE_PROPRE = "Votre lieu a sa propre monnaie sur Fedow."
RAISON_6_CARTES_NFC = "Des cartes NFC sont rattachées à votre lieu."
RAISON_7_RECHARGES = "Votre lieu a eu des échanges avec l'ancien moteur."

# Les textes de la fenêtre de confirmation (spec §5.8).
# / The confirmation window texts.
TEXTE_DE_LA_BASCULE_PHRASE_1 = (
    "Pour activer ce module, votre lieu passe au nouveau moteur de monnaie de TiBillet."
)
TEXTE_DE_LA_BASCULE_PHRASE_2 = (
    "Vos événements, réservations et adhésions ne changent pas."
)
TEXTE_PAS_ENCORE_DISPONIBLE = "Ce module n'est pas encore disponible pour votre lieu"
TEXTE_CONTACTEZ_NOUS = "Contactez l'équipe TiBillet pour lui indiquer que vous souhaitez faire une migration."

CHEMIN_DU_MODULE_DE_LA_BASCULE = "Customers.bascule_vers_v2"


def raisons_en_francais(lieu):
    """
    Appelle `Customers.bascule_vers_v2.raisons_qui_empechent_le_passage_en_v2(lieu)` et rend
    ses phrases en texte français. L'import se fait ici : sans le module, seuls les tests
    qui l'appellent échouent, pas tout le fichier.
    / Calls the reasons function and returns its sentences as French text.
    """
    module_de_la_bascule = importlib.import_module(CHEMIN_DU_MODULE_DE_LA_BASCULE)
    with translation.override("fr"):
        raisons = module_de_la_bascule.raisons_qui_empechent_le_passage_en_v2(lieu)
        raisons_en_texte = []
        for raison in raisons:
            raisons_en_texte.append(str(raison))
    return raisons_en_texte


def texte_lisible_du_html(html_brut):
    """
    Le HTML sans entités (`&#x27;` redevient une apostrophe), les espaces et retours à la
    ligne réduits à un seul espace. Une phrase se cherche alors telle qu'elle s'écrit, que
    le gabarit l'écrive par `{% translate %}` (non échappé) ou par `{{ }}` (échappé).
    / HTML without entities and with collapsed whitespace: sentences can be searched as is.
    """
    texte_sans_entites = html_unescape(html_brut)
    return " ".join(texte_sans_entites.split())


class TestBasculeVersV2(FastTenantTestCase):
    """
    La bascule legacy → v2, dans le lieu dédié `test_verrou_moteur_legacy`.
    / The legacy → v2 switch, in the dedicated test venue.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_verrou_moteur_legacy"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-verrou-moteur-legacy.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test verrou moteur legacy"

    def setUp(self):
        # La transaction du test précédent a été annulée : on se replace sur le lieu.
        # / Back on the venue after the previous rolled-back test.
        connection.set_tenant(self.tenant)
        Configuration.clear_cache()

        # Un schéma cloné n'a pas de ligne de Configuration : on la crée par
        # `bulk_create()` (jamais `save()`, qui écrirait memcached).
        # / A cloned schema has no Configuration row: bulk_create, never save().
        if Configuration.objects.first() is None:
            Configuration.objects.bulk_create(
                [
                    Configuration(
                        pk=Configuration.singleton_instance_id,
                        organisation="Test verrou moteur legacy",
                        slug="test-verrou-moteur-legacy",
                    )
                ]
            )

        # Un gestionnaire du lieu : admin du lieu, pas superadmin.
        # / A venue manager: tenant admin, not superadmin.
        email_unique = f"admin-bascule-{uuid.uuid4().hex[:12]}@tibillet.localhost"
        self.administrateur_du_lieu = TibilletUser.objects.create(
            email=email_unique,
            username=email_unique,
            espece=TibilletUser.TYPE_HUM,
            is_staff=True,
            is_active=True,
        )
        self.administrateur_du_lieu.client_admin.add(self.tenant)

        self.fabrique_de_requetes = RequestFactory()
        self.admin_de_la_configuration = staff_admin_site._registry[Configuration]

    def tearDown(self):
        # Une lecture par `get_solo()` a pu mettre en cache une ligne que l'annulation va
        # effacer : on vide le cache du singleton.
        # / A get_solo() read may have cached a row the rollback will erase.
        connection.set_tenant(self.tenant)
        Configuration.clear_cache()

    # ------------------------------------------------------------------ #
    #  Outils : le lieu / Helpers: the venue                              #
    # ------------------------------------------------------------------ #

    def poser_le_moteur_du_lieu_dedie(self, moteur):
        """
        Pose le moteur du lieu dédié en base par `update()`, puis place la connexion sur
        le `Client` relu en base. Rend ce `Client`.
        / Sets the engine by update(), then puts the re-read Client on the connection.
        """
        Client.objects.filter(pk=self.tenant.pk).update(moteur_monnaie=moteur)
        lieu_relu_en_base = Client.objects.get(pk=self.tenant.pk)
        connection.set_tenant(lieu_relu_en_base)
        return lieu_relu_en_base

    def moteur_du_lieu_lu_en_base(self):
        """Le moteur du lieu dédié, relu en base. / Engine read back from the database."""
        return (
            Client.objects.filter(pk=self.tenant.pk)
            .values_list("moteur_monnaie", flat=True)
            .get()
        )

    def lieu_relu_en_base(self):
        """Le `Client` du lieu dédié, relu en base. / The venue's Client, re-read."""
        return Client.objects.get(pk=self.tenant.pk)

    def autre_lieu(self):
        """
        Un autre lieu, origine d'une monnaie partagée : la ligne `Client` du schéma
        public, jamais un lieu de démo.
        / Another venue for a shared currency: the public schema's Client row.
        """
        return Client.objects.get(schema_name=get_public_schema_name())

    # ------------------------------------------------------------------ #
    #  Outils : ce qui retient un lieu / Helpers: what holds a venue      #
    # ------------------------------------------------------------------ #

    def creer_un_asset_legacy(
        self,
        lien_avec_le_lieu,
        categorie=AssetFedowPublic.TOKEN_LOCAL_FIAT,
        archive=False,
    ):
        """
        Crée une monnaie legacy reliée au lieu dédié, dans la transaction du test.
        - « origine »          : le lieu dédié l'a créée ;
        - « origine_et_federe » : le lieu dédié l'a créée et figure aussi dans
          `federated_with` ;
        - « federe »           : un autre lieu l'a créée, le lieu dédié est dans
          `federated_with` ;
        - « invite »           : un autre lieu l'a créée, le lieu dédié est dans
          `pending_invitations`.
        / Creates a legacy currency linked to the venue, inside the test transaction.
        """
        portefeuille_d_origine = Wallet.objects.create(
            name=f"Portefeuille asset legacy bascule {uuid.uuid4().hex[:8]}"
        )
        if lien_avec_le_lieu in ["origine", "origine_et_federe"]:
            lieu_d_origine = self.tenant
        else:
            lieu_d_origine = self.autre_lieu()

        asset_legacy = AssetFedowPublic.objects.create(
            name=f"Asset legacy bascule {uuid.uuid4().hex[:8]}",
            currency_code="TBV",
            wallet_origin=portefeuille_d_origine,
            origin=lieu_d_origine,
            category=categorie,
            archive=archive,
        )
        if lien_avec_le_lieu in ["federe", "origine_et_federe"]:
            asset_legacy.federated_with.add(self.tenant)
        if lien_avec_le_lieu == "invite":
            asset_legacy.pending_invitations.add(self.tenant)
        return asset_legacy

    def asset_fed_de_la_plateforme(self):
        """
        La monnaie fédérée de toute la plateforme (`FED`). Elle est unique en base
        (contrainte) : on prend celle qui existe, sinon on la crée dans la transaction du
        test, avec un autre lieu pour origine.
        / The platform-wide federated currency (FED), unique: reuse it or create it.
        """
        asset_fed = AssetFedowPublic.objects.filter(
            category=AssetFedowPublic.STRIPE_FED_FIAT
        ).first()
        if asset_fed is not None:
            return asset_fed

        portefeuille_d_origine = Wallet.objects.create(
            name=f"Portefeuille FED bascule {uuid.uuid4().hex[:8]}"
        )
        return AssetFedowPublic.objects.create(
            name=f"FED bascule {uuid.uuid4().hex[:8]}",
            currency_code="EUR",
            wallet_origin=portefeuille_d_origine,
            origin=self.autre_lieu(),
            category=AssetFedowPublic.STRIPE_FED_FIAT,
        )

    def creer_une_carte_nfc(self, lieu_d_origine):
        """Une génération de cartes NFC (`Detail`) d'origine donnée.
        / An NFC card batch (Detail) with the given origin."""
        return Detail.objects.create(
            origine=lieu_d_origine,
            generation=1,
            base_url=f"TEST-BASCULE-{uuid.uuid4().hex[:8]}",
        )

    def creer_une_transaction_fedow(self):
        """Une `FedowTransaction` (cache local d'une transaction de l'ancien Fedow).
        / A FedowTransaction (local cache of an old-Fedow transaction)."""
        return FedowTransaction.objects.create(
            hash=uuid.uuid4().hex + uuid.uuid4().hex,
            datetime=timezone.now(),
        )

    def creer_un_paiement_stripe(
        self,
        categories_des_lignes,
        passe_par_fedow,
        statut=Paiement_stripe.VALID,
    ):
        """
        Un paiement Stripe du lieu, avec une ligne de vente par catégorie de produit
        donnée (liste vide = aucune ligne). S'il « passe par Fedow », il est relié à une
        `FedowTransaction`.
        Chaque produit est créé en catégorie « aucune », puis sa catégorie est posée par
        `update()` : le signal d'un produit d'adhésion appellerait Fedow.
        / A Stripe payment of the venue with one sale line per category; linked to a
        FedowTransaction when it went through Fedow.
        """
        paiement = Paiement_stripe.objects.create(status=statut)
        for categorie_de_la_ligne in categories_des_lignes:
            tarif_vendu = creer_tarif_vendu(nom="Ligne bascule v2")
            Product.objects.filter(pk=tarif_vendu.productsold.product_id).update(
                categorie_article=categorie_de_la_ligne
            )
            ProductSold.objects.filter(pk=tarif_vendu.productsold_id).update(
                categorie_article=categorie_de_la_ligne
            )
            LigneArticle.objects.create(
                pricesold=tarif_vendu,
                qty=Decimal("1"),
                amount=1000,
                status=LigneArticle.VALID,
                paiement_stripe=paiement,
            )
        if passe_par_fedow:
            paiement.fedow_transactions.add(self.creer_une_transaction_fedow())
        return paiement

    @contextlib.contextmanager
    def point_de_sauvegarde_annule(self):
        """
        Un point de sauvegarde annulé à la sortie du bloc : un même test enchaîne des cas
        qui ne se voient pas.
        / A savepoint rolled back on exit: one test runs cases that do not see each other.
        """
        with transaction.atomic():
            yield
            transaction.set_rollback(True)

    # ------------------------------------------------------------------ #
    #  Outils : l'admin / Helpers: the admin                              #
    # ------------------------------------------------------------------ #

    def configuration_en_memoire(self, modules_allumes, **autres_valeurs):
        """
        Une `Configuration` en mémoire, jamais enregistrée : les modules V2 et l'adhésion
        éteints sauf ceux de la liste. Pas de serveur LaBoutik V1 sauf s'il est donné.
        / An in-memory Configuration: modules off except the listed ones.
        """
        valeurs = {"server_cashless": None, "key_cashless": None}
        valeurs.update(autres_valeurs)
        configuration = Configuration(
            pk=Configuration.singleton_instance_id,
            organisation="Test verrou moteur legacy",
            slug="test-verrou-moteur-legacy",
            **valeurs,
        )
        for nom_du_module in MODULES_V2 + ["module_adhesion"]:
            setattr(configuration, nom_du_module, nom_du_module in modules_allumes)
        return configuration

    def construire_une_requete(self, methode, chemin):
        """
        Une requête de `RequestFactory`, avec le gestionnaire, une session et des messages.
        / A RequestFactory request with the manager, a session and message storage.
        """
        if methode == "post":
            requete = self.fabrique_de_requetes.post(chemin)
        else:
            requete = self.fabrique_de_requetes.get(chemin)
        requete.user = self.administrateur_du_lieu
        SessionMiddleware(lambda requete_recue: None).process_request(requete)
        requete._messages = FallbackStorage(requete)
        return requete

    def basculer_un_module(
        self, nom_du_module, configuration, erreur_a_l_enregistrement=None
    ):
        """
        Appelle `ConfigurationAdmin.module_toggle` comme le POST HTMX du tableau de bord.
        `get_solo()` rend la `Configuration` en mémoire ; `save()` est un faux qui note ses
        appels, et lève `erreur_a_l_enregistrement` si elle est donnée.
        Rend la réponse, le faux `save()`, et le texte français des messages d'erreur.
        / Calls module_toggle with an in-memory Configuration and a fake save().
        """
        requete = self.construire_une_requete(
            "post",
            f"/admin/BaseBillet/configuration/module-toggle/{nom_du_module}/",
        )
        with translation.override("fr"):
            with patch.object(Configuration, "get_solo", return_value=configuration):
                with patch.object(
                    Configuration,
                    "save",
                    autospec=True,
                    side_effect=erreur_a_l_enregistrement,
                ) as faux_save:
                    reponse = self.admin_de_la_configuration.module_toggle(
                        requete, nom_du_module
                    )

            textes_des_erreurs = []
            for message in requete._messages:
                if message.level == messages_django.ERROR:
                    textes_des_erreurs.append(str(message.message))

        return reponse, faux_save, textes_des_erreurs

    def fenetre_de_confirmation(self, nom_du_module, configuration):
        """
        Le HTML de la fenêtre de confirmation (`module_toggle_modal`), en français.
        Rend le HTML brut et son texte lisible.
        / The confirmation window HTML (raw, and as readable text).
        """
        requete = self.construire_une_requete(
            "get",
            f"/admin/BaseBillet/configuration/module-toggle-modal/{nom_du_module}/",
        )
        with translation.override("fr"):
            with patch.object(Configuration, "get_solo", return_value=configuration):
                reponse = self.admin_de_la_configuration.module_toggle_modal(
                    requete, nom_du_module
                )
        html_brut = reponse.content.decode()
        return html_brut, texte_lisible_du_html(html_brut)

    def attribut_du_bouton_de_confirmation(self, nom_du_module):
        """L'attribut que porte le bouton de confirmation de la fenêtre.
        / The attribute carried by the window's confirmation button."""
        adresse_de_la_bascule = reverse(
            "staff_admin:configuration-module-toggle", args=[nom_du_module]
        )
        return f'hx-post="{adresse_de_la_bascule}"'

    def cartes_du_tableau_de_bord(self, configuration):
        """
        Les cartes du tableau de bord, lues dans le contexte de `dashboard_callback`,
        rangées par drapeau de module (la carte caisse, type `pos`, sous `module_caisse`).
        / Dashboard cards from dashboard_callback, indexed by module flag.
        """
        requete = RequestFactory().get("/admin/")
        with patch.object(Configuration, "get_solo", return_value=configuration):
            contexte = dashboard.dashboard_callback(requete, {})

        cartes_par_drapeau = {}
        for groupe in contexte["groupes_de_domaines"]:
            for carte in groupe["cartes"]:
                if carte.get("type") == "pos":
                    cartes_par_drapeau["module_caisse"] = carte
                elif carte.get("field"):
                    cartes_par_drapeau[carte["field"]] = carte
        return cartes_par_drapeau

    def html_de_la_carte(self, carte):
        """Le HTML d'une carte rendu en français, brut et en texte lisible.
        / A card's HTML in French, raw and as readable text."""
        with translation.override("fr"):
            html_brut = render_to_string(
                "admin/partials/dashboard_module_card.html", {"carte": carte}
            )
        return html_brut, texte_lisible_du_html(html_brut)

    def phrase_fixe_du_verrou(self):
        """La phrase fixe du verrou (§5.1), en français. / The fixed lock sentence."""
        with translation.override("fr"):
            return str(MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY)

    # ================================================================== #
    #  1 à 9 — Les raisons qui retiennent un lieu                         #
    #  / 1 to 9 — The reasons that hold a venue                           #
    # ================================================================== #

    def test_aucune_raison_pour_un_lieu_neuf_legacy(self):
        """
        Le lieu dédié, legacy, sans rien de l'ancien Fedow : aucune raison.
        / A legacy venue with nothing from the old Fedow: no reason.
        """
        lieu = self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)

        assert raisons_en_francais(lieu) == []

    def test_raison_lieu_meta(self):
        """
        Le lieu est l'agenda partagé de TiBillet (`Client.META`) : la raison 1, seule.
        / The venue is the shared agenda (META): reason 1 only.
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        Client.objects.filter(pk=self.tenant.pk).update(categorie=Client.META)

        assert raisons_en_francais(self.lieu_relu_en_base()) == [
            RAISON_1_AGENDA_PARTAGE
        ]

    def test_raison_laboutik_v1(self):
        """
        `Configuration.server_cashless` renseigné : la raison 2, seule. Une adresse vide
        n'est pas renseignée : aucune raison.
        La `Configuration` est modifiée par `update()` ; le cache est vidé avant chaque
        lecture, pour que `get_solo()` relise la base s'il est utilisé.
        / server_cashless set: reason 2 only; an empty address is not set.
        """
        lieu = self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)

        Configuration.objects.update(server_cashless="https://laboutik-v1.example.org")
        Configuration.clear_cache()
        assert raisons_en_francais(lieu) == [RAISON_2_LABOUTIK_V1]

        Configuration.objects.update(server_cashless="")
        Configuration.clear_cache()
        assert raisons_en_francais(lieu) == []

    def test_raison_monnaie_d_un_autre_lieu_acceptee(self):
        """
        Le lieu est fédéré à la monnaie legacy d'un autre lieu : la raison 3, seule, que la
        monnaie soit archivée ou non.
        Le lieu fédéré à sa PROPRE monnaie fiduciaire (`TLF`, il en est l'origine et figure
        dans son `federated_with`) : exactement la raison 5, sans la raison 3 (la raison 3
        exige une origine autre que le lieu).
        Le lieu fédéré à la monnaie `FED` de la plateforme, ou à une monnaie `SUB` ou `BDG`
        d'un autre lieu : aucune raison (catégories exclues de la raison 3).
        / Federated to another venue's legacy currency (archived or not): reason 3 only;
        FED, SUB and BDG are excluded.
        """
        lieu = self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        constats_faux = []

        for archive in [False, True]:
            with self.point_de_sauvegarde_annule():
                self.creer_un_asset_legacy("federe", archive=archive)
                raisons = raisons_en_francais(lieu)
                if raisons != [RAISON_3_MONNAIE_D_UN_AUTRE_LIEU]:
                    constats_faux.append(f"fédéré, archive={archive} : {raisons}")

        with self.point_de_sauvegarde_annule():
            self.creer_un_asset_legacy(
                "origine_et_federe", categorie=AssetFedowPublic.TOKEN_LOCAL_FIAT
            )
            raisons = raisons_en_francais(lieu)
            if raisons != [RAISON_5_MONNAIE_PROPRE]:
                constats_faux.append(f"fédéré à sa propre monnaie TLF : {raisons}")

        with self.point_de_sauvegarde_annule():
            self.asset_fed_de_la_plateforme().federated_with.add(self.tenant)
            raisons = raisons_en_francais(lieu)
            if raisons != []:
                constats_faux.append(f"fédéré à FED : {raisons}")

        for categorie in [AssetFedowPublic.SUBSCRIPTION, AssetFedowPublic.BADGE]:
            with self.point_de_sauvegarde_annule():
                self.creer_un_asset_legacy("federe", categorie=categorie)
                raisons = raisons_en_francais(lieu)
                if raisons != []:
                    constats_faux.append(
                        f"fédéré à {categorie} d'un autre lieu : {raisons}"
                    )

        assert constats_faux == [], "\n".join(constats_faux)

    def test_raison_invitation_en_attente(self):
        """
        Le lieu est invité sur la monnaie legacy d'un autre lieu : la raison 4, seule, que
        la monnaie soit archivée ou non. Une invitation sur la monnaie `FED`, ou sur une
        monnaie `SUB` ou `BDG` : aucune raison (mêmes catégories exclues qu'en 3).
        / Invited to another venue's legacy currency (archived or not): reason 4 only;
        FED, SUB and BDG are excluded.
        """
        lieu = self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        constats_faux = []

        for archive in [False, True]:
            with self.point_de_sauvegarde_annule():
                self.creer_un_asset_legacy("invite", archive=archive)
                raisons = raisons_en_francais(lieu)
                if raisons != [RAISON_4_INVITATION]:
                    constats_faux.append(f"invité, archive={archive} : {raisons}")

        with self.point_de_sauvegarde_annule():
            self.asset_fed_de_la_plateforme().pending_invitations.add(self.tenant)
            raisons = raisons_en_francais(lieu)
            if raisons != []:
                constats_faux.append(f"invité sur FED : {raisons}")

        for categorie in [AssetFedowPublic.SUBSCRIPTION, AssetFedowPublic.BADGE]:
            with self.point_de_sauvegarde_annule():
                self.creer_un_asset_legacy("invite", categorie=categorie)
                raisons = raisons_en_francais(lieu)
                if raisons != []:
                    constats_faux.append(f"invité sur {categorie} : {raisons}")

        assert constats_faux == [], "\n".join(constats_faux)

    def test_raison_monnaie_propre(self):
        """
        Le lieu a créé une monnaie legacy :
        - fiduciaire (`TLF`), cadeau (`TNF`), temps (`TIM`), fidélité (`FID`) : la
          raison 5, seule ; une `TLF` archivée aussi ;
        - adhésion (`SUB`), badge (`BDG`) : aucune raison, archivée ou non.
        `FED` n'est pas créée : elle est unique en base (contrainte).
        / Own legacy currency: reason 5 except SUB and BDG; archived included.
        """
        lieu = self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        constats_faux = []

        cas_qui_retiennent = [
            (AssetFedowPublic.TOKEN_LOCAL_FIAT, False),
            (AssetFedowPublic.TOKEN_LOCAL_FIAT, True),
            (AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT, False),
            (AssetFedowPublic.TIME, False),
            (AssetFedowPublic.FIDELITY, False),
        ]
        for categorie, archive in cas_qui_retiennent:
            with self.point_de_sauvegarde_annule():
                self.creer_un_asset_legacy(
                    "origine", categorie=categorie, archive=archive
                )
                raisons = raisons_en_francais(lieu)
                if raisons != [RAISON_5_MONNAIE_PROPRE]:
                    constats_faux.append(f"{categorie}, archive={archive} : {raisons}")

        cas_qui_ne_retiennent_pas = [
            (AssetFedowPublic.SUBSCRIPTION, False),
            (AssetFedowPublic.SUBSCRIPTION, True),
            (AssetFedowPublic.BADGE, False),
            (AssetFedowPublic.BADGE, True),
        ]
        for categorie, archive in cas_qui_ne_retiennent_pas:
            with self.point_de_sauvegarde_annule():
                self.creer_un_asset_legacy(
                    "origine", categorie=categorie, archive=archive
                )
                raisons = raisons_en_francais(lieu)
                if raisons != []:
                    constats_faux.append(f"{categorie}, archive={archive} : {raisons}")

        assert constats_faux == [], "\n".join(constats_faux)

    def test_raison_cartes_nfc(self):
        """
        Une génération de cartes NFC a le lieu pour origine (`Detail.origine`) : la
        raison 6, seule. Les cartes d'un autre lieu : aucune raison.
        / NFC cards whose origin is the venue: reason 6; another venue's cards: none.
        """
        lieu = self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        constats_faux = []

        with self.point_de_sauvegarde_annule():
            self.creer_une_carte_nfc(self.tenant)
            raisons = raisons_en_francais(lieu)
            if raisons != [RAISON_6_CARTES_NFC]:
                constats_faux.append(f"cartes du lieu : {raisons}")

        with self.point_de_sauvegarde_annule():
            self.creer_une_carte_nfc(self.autre_lieu())
            raisons = raisons_en_francais(lieu)
            if raisons != []:
                constats_faux.append(f"cartes d'un autre lieu : {raisons}")

        assert constats_faux == [], "\n".join(constats_faux)

    def test_raison_recharge_stripe_passee_par_fedow(self):
        """
        Un paiement Stripe du lieu relié à au moins une `FedowTransaction`, quel que soit
        son statut, retient le lieu (raison 7, seule) s'il a au moins une ligne d'un
        produit autre qu'une adhésion, ou aucune ligne :
        - une recharge : raison 7 ;
        - une adhésion et une recharge dans le même paiement : raison 7 ;
        - aucune ligne : raison 7 ;
        - une recharge, paiement non validé (statut « lien non généré ») : raison 7 ;
        - seulement une adhésion (`Product.ADHESION`) : aucune raison ;
        - une recharge sans `FedowTransaction` : aucune raison.
        / Stripe payment through Fedow with a non-membership line or no line: reason 7,
        whatever its status; membership only, or no Fedow transaction: none.
        """
        lieu = self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        constats_faux = []

        cas_qui_retiennent = [
            ("recharge", [Product.RECHARGE_CASHLESS], Paiement_stripe.VALID),
            (
                "adhésion et recharge",
                [Product.ADHESION, Product.RECHARGE_CASHLESS],
                Paiement_stripe.VALID,
            ),
            ("aucune ligne", [], Paiement_stripe.VALID),
            ("recharge non validée", [Product.RECHARGE_CASHLESS], Paiement_stripe.NON),
        ]
        for nom_du_cas, categories_des_lignes, statut in cas_qui_retiennent:
            with self.point_de_sauvegarde_annule():
                self.creer_un_paiement_stripe(
                    categories_des_lignes, passe_par_fedow=True, statut=statut
                )
                raisons = raisons_en_francais(lieu)
                if raisons != [RAISON_7_RECHARGES]:
                    constats_faux.append(f"{nom_du_cas} passée par Fedow : {raisons}")

        with self.point_de_sauvegarde_annule():
            self.creer_un_paiement_stripe([Product.ADHESION], passe_par_fedow=True)
            raisons = raisons_en_francais(lieu)
            if raisons != []:
                constats_faux.append(f"adhésion seule passée par Fedow : {raisons}")

        with self.point_de_sauvegarde_annule():
            self.creer_un_paiement_stripe(
                [Product.RECHARGE_CASHLESS], passe_par_fedow=False
            )
            raisons = raisons_en_francais(lieu)
            if raisons != []:
                constats_faux.append(f"recharge sans transaction Fedow : {raisons}")

        assert constats_faux == [], "\n".join(constats_faux)

    def test_les_adhesions_envoyees_a_fedow_ne_retiennent_pas(self):
        """
        Une adhésion reliée à une `FedowTransaction` (`Membership.fedow_transactions`), et
        une `FedowTransaction` seule (cache de l'historique « Mon compte ») : aucune raison.
        / Memberships sent to Fedow and a lone FedowTransaction: no reason.
        """
        lieu = self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)

        adhesion = Membership.objects.create(
            status=Membership.ONCE,
            first_name="Ada",
            last_name="Lovelace",
        )
        adhesion.fedow_transactions.add(self.creer_une_transaction_fedow())
        self.creer_une_transaction_fedow()

        assert raisons_en_francais(lieu) == []

    def test_toutes_les_raisons_dans_l_ordre_une_phrase_chacune(self):
        """
        Les sept raisons à la fois, deux fois chacune quand c'est possible (deux monnaies,
        deux générations de cartes, deux paiements) : les sept phrases, dans l'ordre du
        tableau §5.8, une seule fois chacune.
        / All seven reasons at once, some twice: seven sentences, in order, once each.
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        Client.objects.filter(pk=self.tenant.pk).update(categorie=Client.META)
        Configuration.objects.update(server_cashless="https://laboutik-v1.example.org")
        Configuration.clear_cache()
        for _numero in range(2):
            self.creer_un_asset_legacy("federe")
            self.creer_un_asset_legacy("invite")
            self.creer_un_asset_legacy("origine")
            self.creer_une_carte_nfc(self.tenant)
            self.creer_un_paiement_stripe(
                [Product.RECHARGE_CASHLESS], passe_par_fedow=True
            )

        assert raisons_en_francais(self.lieu_relu_en_base()) == [
            RAISON_1_AGENDA_PARTAGE,
            RAISON_2_LABOUTIK_V1,
            RAISON_3_MONNAIE_D_UN_AUTRE_LIEU,
            RAISON_4_INVITATION,
            RAISON_5_MONNAIE_PROPRE,
            RAISON_6_CARTES_NFC,
            RAISON_7_RECHARGES,
        ]

    # ================================================================== #
    #  10 à 13 — module_toggle                                            #
    # ================================================================== #

    def test_allumer_la_caisse_fait_basculer_un_lieu_sans_raison(self):
        """
        Lieu legacy sans raison, tous les modules éteints. Allumer la caisse :
        - le moteur passe à v2 en base, et sur `connection.tenant` ;
        - la caisse ET la monnaie locale sont allumées, un seul `save()` ;
        - aucun message d'erreur, réponse `HX-Refresh` ;
        - un `logger.info` nomme le lieu et le module.
        Puis, pour chacun des trois autres modules V2, le lieu remis en legacy : allumer le
        module fait aussi basculer le lieu.
        / Legacy venue, no reason: switching on the POS moves the venue to v2.
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        configuration = self.configuration_en_memoire([])

        with self.assertLogs("Administration.admin_tenant", level="INFO") as journal:
            reponse, faux_save, textes_des_erreurs = self.basculer_un_module(
                "module_caisse", configuration
            )

        assert self.moteur_du_lieu_lu_en_base() == MOTEUR_V2
        assert connection.tenant.moteur_monnaie == MOTEUR_V2
        assert configuration.module_caisse is True
        assert configuration.module_monnaie_locale is True
        assert faux_save.call_count == 1
        assert textes_des_erreurs == []
        assert reponse["HX-Refresh"] == "true"

        lignes_qui_nomment_la_bascule = []
        for ligne_du_journal in journal.records:
            texte_de_la_ligne = ligne_du_journal.getMessage()
            nomme_le_lieu = (
                self.tenant.schema_name in texte_de_la_ligne
                or self.tenant.name in texte_de_la_ligne
            )
            if nomme_le_lieu and "module_caisse" in texte_de_la_ligne:
                lignes_qui_nomment_la_bascule.append(texte_de_la_ligne)
        assert lignes_qui_nomment_la_bascule != [], journal.output

        constats_faux = []
        for nom_du_module in [
            "module_monnaie_locale",
            "module_kiosk",
            "module_tireuse",
        ]:
            self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
            configuration = self.configuration_en_memoire([])
            _reponse, faux_save, textes_des_erreurs = self.basculer_un_module(
                nom_du_module, configuration
            )
            if self.moteur_du_lieu_lu_en_base() != MOTEUR_V2:
                constats_faux.append(f"{nom_du_module} : moteur pas v2")
            if getattr(configuration, nom_du_module) is not True:
                constats_faux.append(f"{nom_du_module} : module pas allumé")
            if faux_save.call_count != 1:
                constats_faux.append(
                    f"{nom_du_module} : save() x{faux_save.call_count}"
                )
            if textes_des_erreurs:
                constats_faux.append(f"{nom_du_module} : erreurs {textes_des_erreurs}")

        assert constats_faux == [], "\n".join(constats_faux)

    def test_allumer_un_module_v2_reste_refuse_avec_une_raison(self):
        """
        Lieu legacy retenu par ses cartes NFC (raison 6). Pour chacun des quatre modules
        V2 : refus avant toute écriture.
        - le moteur reste legacy en base ;
        - les drapeaux restent éteints, `save()` n'est jamais appelé ;
        - un message d'erreur : « pas encore disponible », la raison, la phrase de fin (« Contactez l'équipe TiBillet… ») ;
          réponse `HX-Refresh`.
        Puis un lieu retenu seulement par LaBoutik V1 (raison 2), qui allume la caisse par
        un POST direct : même refus, le message cite LaBoutik V1. L'adresse V1 est posée en
        base ET sur la configuration en mémoire.
        / Legacy venue with a reason: every V2 module refused, engine unchanged, message
        quotes the reason.
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        constats_faux = []

        with self.point_de_sauvegarde_annule():
            self.creer_une_carte_nfc(self.tenant)
            for nom_du_module in MODULES_V2:
                configuration = self.configuration_en_memoire([])
                reponse, faux_save, textes_des_erreurs = self.basculer_un_module(
                    nom_du_module, configuration
                )
                if self.moteur_du_lieu_lu_en_base() != MOTEUR_LEGACY:
                    constats_faux.append(f"{nom_du_module} : moteur changé")
                for nom_du_drapeau in MODULES_V2:
                    if getattr(configuration, nom_du_drapeau) is not False:
                        constats_faux.append(
                            f"{nom_du_module} : {nom_du_drapeau} allumé"
                        )
                if faux_save.call_count != 0:
                    constats_faux.append(f"{nom_du_module} : save() appelé")
                texte_des_erreurs = " ".join(textes_des_erreurs)
                for texte_attendu in [
                    TEXTE_PAS_ENCORE_DISPONIBLE,
                    RAISON_6_CARTES_NFC,
                    TEXTE_CONTACTEZ_NOUS,
                ]:
                    if texte_attendu not in texte_des_erreurs:
                        constats_faux.append(
                            f"{nom_du_module} : « {texte_attendu} » absent de "
                            f"{textes_des_erreurs}"
                        )
                if reponse.get("HX-Refresh") != "true":
                    constats_faux.append(f"{nom_du_module} : pas de HX-Refresh")

        adresse_du_serveur_v1 = "https://laboutik-v1.example.org"
        Configuration.objects.update(server_cashless=adresse_du_serveur_v1)
        Configuration.clear_cache()
        configuration = self.configuration_en_memoire(
            [], server_cashless=adresse_du_serveur_v1
        )
        _reponse, faux_save, textes_des_erreurs = self.basculer_un_module(
            "module_caisse", configuration
        )
        if self.moteur_du_lieu_lu_en_base() != MOTEUR_LEGACY:
            constats_faux.append("LaBoutik V1 : moteur changé")
        if configuration.module_caisse is not False:
            constats_faux.append("LaBoutik V1 : caisse allumée")
        if faux_save.call_count != 0:
            constats_faux.append("LaBoutik V1 : save() appelé")
        if RAISON_2_LABOUTIK_V1 not in " ".join(textes_des_erreurs):
            constats_faux.append(
                f"LaBoutik V1 : raison absente de {textes_des_erreurs}"
            )

        assert constats_faux == [], "\n".join(constats_faux)

    def test_bascule_annulee_si_l_enregistrement_echoue(self):
        """
        Lieu legacy sans raison. `Configuration.save()` lève une `ValidationError`
        (simulée, comme un SEPA refusé par Stripe) pendant l'allumage du kiosk : la bascule
        est annulée avec le reste, le moteur reste legacy en base ET sur
        `connection.tenant`. Le refus suit la règle existante de la méthode : un message
        d'erreur, réponse `HX-Refresh`.
        / save() fails: the engine switch is rolled back too; engine stays legacy.
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        configuration = self.configuration_en_memoire([])

        reponse, faux_save, textes_des_erreurs = self.basculer_un_module(
            "module_kiosk",
            configuration,
            erreur_a_l_enregistrement=ValidationError(
                "Erreur simulée à l'enregistrement"
            ),
        )

        assert faux_save.call_count == 1
        assert self.moteur_du_lieu_lu_en_base() == MOTEUR_LEGACY
        assert connection.tenant.moteur_monnaie == MOTEUR_LEGACY
        assert textes_des_erreurs != []
        assert reponse["HX-Refresh"] == "true"

    def test_eteindre_et_lieu_v2_inchanges(self):
        """
        - Lieu legacy sans raison, modules V2 allumés en base : éteindre le kiosk est
          permis et ne fait PAS basculer le lieu (moteur legacy).
        - Lieu legacy sans raison : allumer un module qui n'est pas V2 (adhésions) ne fait
          pas basculer le lieu.
        - Lieu v2 : allumer puis éteindre le kiosk fonctionne comme avant ; le lieu reste
          v2, il ne repasse jamais legacy.
        - Lieu v2 dont l'enregistrement échoue (`ValidationError` simulée) : il reste v2,
          en base ET sur `connection.tenant`.
        / Switching off never switches the engine; a non-V2 module never does; a v2
        venue stays v2, even when the save fails.
        """
        constats_faux = []

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        configuration = self.configuration_en_memoire(MODULES_V2)
        _reponse, faux_save, textes_des_erreurs = self.basculer_un_module(
            "module_kiosk", configuration
        )
        if configuration.module_kiosk is not False:
            constats_faux.append("legacy, éteindre le kiosk : pas éteint")
        if faux_save.call_count != 1 or textes_des_erreurs:
            constats_faux.append(f"legacy, éteindre le kiosk : {textes_des_erreurs}")
        if self.moteur_du_lieu_lu_en_base() != MOTEUR_LEGACY:
            constats_faux.append("legacy, éteindre le kiosk : le lieu a basculé")

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        configuration = self.configuration_en_memoire([])
        _reponse, faux_save, textes_des_erreurs = self.basculer_un_module(
            "module_adhesion", configuration
        )
        if configuration.module_adhesion is not True:
            constats_faux.append("legacy, allumer les adhésions : pas allumé")
        if self.moteur_du_lieu_lu_en_base() != MOTEUR_LEGACY:
            constats_faux.append("legacy, allumer les adhésions : le lieu a basculé")

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        configuration = self.configuration_en_memoire([])
        for etape in ["allumer", "éteindre"]:
            _reponse, faux_save, textes_des_erreurs = self.basculer_un_module(
                "module_kiosk", configuration
            )
            module_attendu_allume = etape == "allumer"
            if configuration.module_kiosk is not module_attendu_allume:
                constats_faux.append(f"v2, {etape} le kiosk : drapeau faux")
            if faux_save.call_count != 1 or textes_des_erreurs:
                constats_faux.append(f"v2, {etape} le kiosk : {textes_des_erreurs}")
            if self.moteur_du_lieu_lu_en_base() != MOTEUR_V2:
                constats_faux.append(f"v2, {etape} le kiosk : le lieu n'est plus v2")

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        _reponse, _faux_save, textes_des_erreurs = self.basculer_un_module(
            "module_kiosk",
            self.configuration_en_memoire([]),
            erreur_a_l_enregistrement=ValidationError("Erreur simulée"),
        )
        if not textes_des_erreurs:
            constats_faux.append("v2, enregistrement en échec : pas de message")
        if self.moteur_du_lieu_lu_en_base() != MOTEUR_V2:
            constats_faux.append("v2, enregistrement en échec : plus v2 en base")
        if connection.tenant.moteur_monnaie != MOTEUR_V2:
            constats_faux.append(
                "v2, enregistrement en échec : plus v2 sur la connexion"
            )

        assert constats_faux == [], "\n".join(constats_faux)

    # ================================================================== #
    #  15-5-bis — échecs de l'enregistrement et double clic               #
    #  / 15-5-bis — save failures and double click                        #
    # ================================================================== #

    def preparer_la_configuration_en_base_avec_un_sepa_refuse(self):
        """
        La `Configuration` du lieu dédié EN BASE (par `update()`) : modules V2 et adhésions
        éteints, SEPA demandé. Le cache du singleton est vidé : `get_solo()` relit la base.
        / The venue's Configuration in the database: modules off, SEPA requested.
        """
        valeurs_des_drapeaux = {"stripe_accept_sepa": True}
        for nom_du_module in MODULES_V2 + ["module_adhesion"]:
            valeurs_des_drapeaux[nom_du_module] = False
        Configuration.objects.update(**valeurs_des_drapeaux)
        Configuration.clear_cache()

    def basculer_un_module_avec_le_vrai_enregistrement(self, nom_du_module):
        """
        Appelle `ConfigurationAdmin.module_toggle` avec le VRAI `get_solo()` et le VRAI
        `Configuration.save()`. Seule la réponse de Stripe est simulée : la capacité SEPA
        est « inactive ». `save()` enregistre alors la ligne (SEPA remis à faux), écrit le
        cache du singleton, puis lève la `ValidationError` du SEPA.
        Le cache touché est celui du lieu dédié (clé par schéma) ; `tearDown` le vide.
        Rend la réponse et le texte français des messages d'erreur.
        / Calls module_toggle with the real get_solo() and save(); only Stripe is faked
        (SEPA capability inactive).
        """
        requete = self.construire_une_requete(
            "post",
            f"/admin/BaseBillet/configuration/module-toggle/{nom_du_module}/",
        )
        with translation.override("fr"):
            with patch.object(
                Configuration, "check_stripe_sepa_capability", return_value=False
            ):
                reponse = self.admin_de_la_configuration.module_toggle(
                    requete, nom_du_module
                )

            textes_des_erreurs = []
            for message in requete._messages:
                if message.level == messages_django.ERROR:
                    textes_des_erreurs.append(str(message.message))

        return reponse, textes_des_erreurs

    def test_bascule_en_echec_ne_laisse_pas_la_caisse_allumee_dans_le_cache(self):
        """
        Lieu legacy sans raison, SEPA demandé mais refusé par Stripe. Allumer la caisse
        avec le vrai `Configuration.save()` : `save()` écrit la ligne et le cache, puis
        lève la `ValidationError`. La transaction de la bascule annule la ligne :
        - le lieu est toujours legacy, en base et sur `connection.tenant` ;
        - la caisse et la monnaie locale sont éteintes en base ;
        - `Configuration.get_solo()` relu donne aussi la caisse éteinte : le cache du
          singleton ne garde pas l'objet annulé ;
        - un message d'erreur (celui du SEPA).
        / A failed switch must not leave the POS switched on in the singleton cache.
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        self.preparer_la_configuration_en_base_avec_un_sepa_refuse()

        _reponse, textes_des_erreurs = (
            self.basculer_un_module_avec_le_vrai_enregistrement("module_caisse")
        )

        constats_faux = []
        if self.moteur_du_lieu_lu_en_base() != MOTEUR_LEGACY:
            constats_faux.append("le lieu n'est plus legacy en base")
        if connection.tenant.moteur_monnaie != MOTEUR_LEGACY:
            constats_faux.append("le lieu n'est plus legacy sur la connexion")
        configuration_en_base = Configuration.objects.first()
        if (
            configuration_en_base.module_caisse
            or configuration_en_base.module_monnaie_locale
        ):
            constats_faux.append("caisse ou monnaie locale allumée en base")
        configuration_relue = Configuration.get_solo()
        if configuration_relue.module_caisse:
            constats_faux.append("get_solo() rend la caisse allumée (cache périmé)")
        if configuration_relue.module_monnaie_locale:
            constats_faux.append(
                "get_solo() rend la monnaie locale allumée (cache périmé)"
            )
        if not textes_des_erreurs:
            constats_faux.append("pas de message d'erreur")

        assert constats_faux == [], "\n".join(constats_faux)

    def test_echec_hors_bascule_garde_l_enregistrement_partiel(self):
        """
        Sans bascule demandée, l'échec du SEPA garde le comportement de la méthode :
        `save()` a déjà enregistré la ligne (le module ET le SEPA remis à faux), puis
        lève l'erreur, affichée en message. Rien n'est annulé.
        - lieu v2 qui allume le kiosk : kiosk allumé en base, SEPA éteint, lieu v2 ;
        - lieu legacy sans raison qui allume les adhésions (module qui n'est pas V2) :
          adhésions allumées en base, SEPA éteint, lieu legacy.
        Vrai `Configuration.save()`, Stripe simulé (capacité SEPA « inactive »).
        / Without a switch, the partial save of the method is kept (nothing rolled back).
        """
        constats_faux = []
        cas_a_verifier = [
            (MOTEUR_V2, "module_kiosk"),
            (MOTEUR_LEGACY, "module_adhesion"),
        ]
        for moteur, nom_du_module in cas_a_verifier:
            with self.point_de_sauvegarde_annule():
                self.poser_le_moteur_du_lieu_dedie(moteur)
                self.preparer_la_configuration_en_base_avec_un_sepa_refuse()

                _reponse, textes_des_erreurs = (
                    self.basculer_un_module_avec_le_vrai_enregistrement(nom_du_module)
                )

                contexte = f"{moteur}, {nom_du_module}"
                configuration_en_base = Configuration.objects.first()
                if getattr(configuration_en_base, nom_du_module) is not True:
                    constats_faux.append(f"{contexte} : module pas enregistré")
                if configuration_en_base.stripe_accept_sepa is not False:
                    constats_faux.append(f"{contexte} : SEPA pas remis à faux en base")
                if self.moteur_du_lieu_lu_en_base() != moteur:
                    constats_faux.append(f"{contexte} : le moteur a changé")
                if not textes_des_erreurs:
                    constats_faux.append(f"{contexte} : pas de message d'erreur")
            Configuration.clear_cache()

        assert constats_faux == [], "\n".join(constats_faux)

    def test_stripe_interroge_avant_le_verrou_de_la_ligne_du_lieu(self):
        """
        Pendant une bascule, `Configuration.save()` interroge Stripe (capacité SEPA)
        quand le SEPA est demandé. Cet appel réseau part AVANT la mise à jour de la ligne
        `Customers_client` du lieu : la ligne n'est pas verrouillée pendant l'attente de
        Stripe. Au moment de l'appel, le moteur lu en base est donc encore legacy.
        Stripe simulé : la capacité SEPA répond « active », la bascule aboutit (lieu v2,
        caisse allumée en base, aucun message d'erreur). Vrai `get_solo()`, vrai `save()`.
        / Stripe is called before the venue's Client row is updated (no lock held).
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        self.preparer_la_configuration_en_base_avec_un_sepa_refuse()

        moteurs_lus_pendant_l_appel_a_stripe = []

        def capacite_sepa_active_qui_note_le_moteur(configuration_appelante):
            moteur_lu_en_base = self.moteur_du_lieu_lu_en_base()
            moteurs_lus_pendant_l_appel_a_stripe.append(moteur_lu_en_base)
            return True

        requete = self.construire_une_requete(
            "post", "/admin/BaseBillet/configuration/module-toggle/module_caisse/"
        )
        with translation.override("fr"):
            with patch.object(
                Configuration,
                "check_stripe_sepa_capability",
                autospec=True,
                side_effect=capacite_sepa_active_qui_note_le_moteur,
            ):
                self.admin_de_la_configuration.module_toggle(requete, "module_caisse")
            textes_des_erreurs = []
            for message in requete._messages:
                if message.level == messages_django.ERROR:
                    textes_des_erreurs.append(str(message.message))

        assert moteurs_lus_pendant_l_appel_a_stripe == [MOTEUR_LEGACY]
        assert self.moteur_du_lieu_lu_en_base() == MOTEUR_V2
        assert Configuration.objects.first().module_caisse is True
        assert textes_des_erreurs == []

    def test_autre_erreur_pendant_la_bascule_remet_legacy_et_remonte(self):
        """
        Lieu legacy sans raison. `Configuration.save()` lève une erreur qui n'est pas une
        `ValidationError` (simulée) pendant l'allumage du kiosk :
        - l'erreur remonte (pas de message à la place d'une vraie panne) ;
        - le lieu est toujours legacy en base ET sur `connection.tenant`.
        / Any other error: engine back to legacy on the connection, then the error rises.
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)

        with self.assertRaises(RuntimeError):
            self.basculer_un_module(
                "module_kiosk",
                self.configuration_en_memoire([]),
                erreur_a_l_enregistrement=RuntimeError("Panne simulée"),
            )

        assert self.moteur_du_lieu_lu_en_base() == MOTEUR_LEGACY
        assert connection.tenant.moteur_monnaie == MOTEUR_LEGACY

    def test_double_clic_une_seule_bascule_et_un_seul_journal(self):
        """
        Lieu legacy sans raison. Deux POST d'allumage de la caisse :
        1. Deux POST partis en même temps (double clic) : la seconde requête a lu le lieu
           legacy et la caisse éteinte AVANT que la première ne finisse. Après les deux :
           le lieu est v2, la caisse est allumée, et le journal ne compte qu'UNE ligne
           « Bascule en un clic » (la seconde mise à jour ne trouve plus de ligne legacy).
        2. Deux POST l'un après l'autre : le second voit un lieu v2 et la caisse allumée.
           C'est un interrupteur : il ÉTEINT la caisse, comme pour tout lieu v2. La
           monnaie locale reste allumée, le lieu reste v2, aucun nouveau journal.
        / Double click: one switch, one log line; a later second POST switches the POS off.
        """
        constats_faux = []

        # 1 — Deux requêtes en même temps. / 1 — Two concurrent requests.
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        lieu_lu_par_la_seconde_requete = self.lieu_relu_en_base()
        configuration_de_la_premiere_requete = self.configuration_en_memoire([])
        configuration_de_la_seconde_requete = self.configuration_en_memoire([])

        with self.assertLogs("Administration.admin_tenant", level="INFO") as journal:
            self.basculer_un_module(
                "module_caisse", configuration_de_la_premiere_requete
            )
            connection.set_tenant(lieu_lu_par_la_seconde_requete)
            self.basculer_un_module(
                "module_caisse", configuration_de_la_seconde_requete
            )

        lignes_de_bascule = []
        for ligne_du_journal in journal.records:
            if "Bascule en un clic" in ligne_du_journal.getMessage():
                lignes_de_bascule.append(ligne_du_journal.getMessage())
        if len(lignes_de_bascule) != 1:
            constats_faux.append(f"en même temps : {len(lignes_de_bascule)} journaux")
        if self.moteur_du_lieu_lu_en_base() != MOTEUR_V2:
            constats_faux.append("en même temps : le lieu n'est pas v2")
        if configuration_de_la_premiere_requete.module_caisse is not True:
            constats_faux.append("en même temps : caisse éteinte après la 1re requête")
        if configuration_de_la_seconde_requete.module_caisse is not True:
            constats_faux.append("en même temps : caisse éteinte après la 2e requête")

        # 2 — Deux requêtes l'une après l'autre. / 2 — Two successive requests.
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        configuration = self.configuration_en_memoire([])
        with self.assertLogs("Administration.admin_tenant", level="INFO") as journal:
            self.basculer_un_module("module_caisse", configuration)
            if configuration.module_caisse is not True:
                constats_faux.append("l'un après l'autre : caisse éteinte après le 1er")
            self.poser_le_moteur_du_lieu_dedie(self.moteur_du_lieu_lu_en_base())
            self.basculer_un_module("module_caisse", configuration)

        lignes_de_bascule = []
        for ligne_du_journal in journal.records:
            if "Bascule en un clic" in ligne_du_journal.getMessage():
                lignes_de_bascule.append(ligne_du_journal.getMessage())
        if len(lignes_de_bascule) != 1:
            constats_faux.append(
                f"l'un après l'autre : {len(lignes_de_bascule)} journaux"
            )
        if configuration.module_caisse is not False:
            constats_faux.append(
                "l'un après l'autre : le 2e POST n'a pas éteint la caisse"
            )
        if configuration.module_monnaie_locale is not True:
            constats_faux.append("l'un après l'autre : monnaie locale éteinte")
        if self.moteur_du_lieu_lu_en_base() != MOTEUR_V2:
            constats_faux.append("l'un après l'autre : le lieu n'est plus v2")

        assert constats_faux == [], "\n".join(constats_faux)

    # ================================================================== #
    #  14 — La fenêtre de confirmation                                    #
    #  / 14 — The confirmation window                                     #
    # ================================================================== #

    def test_fenetre_de_confirmation_les_deux_textes(self):
        """
        Module V2 éteint, à allumer (chacun des quatre) :
        - lieu legacy sans raison : le texte de la bascule (ses deux phrases) et le bouton
          de confirmation ;
        - lieu legacy retenu (monnaie propre, cartes NFC) : « pas encore disponible », les
          deux raisons, la phrase de fin (« Contactez l'équipe TiBillet… »), et PAS de bouton de confirmation ni de texte
          de bascule ;
        - lieu v2 (témoin) : le bouton, sans texte de bascule ni raison.
        Puis, lieu legacy sans raison, un module qui n'est pas V2 (adhésions) : le bouton,
        sans texte de bascule.
        / Legacy without reason: switch text + button; with reasons: reasons, no button;
        v2 and non-V2 module: button, no switch text.
        """
        constats_faux = []

        def textes_de_la_bascule_presents(texte):
            return (
                TEXTE_DE_LA_BASCULE_PHRASE_1 in texte
                and TEXTE_DE_LA_BASCULE_PHRASE_2 in texte
            )

        def textes_de_la_bascule_absents(texte):
            return (
                TEXTE_DE_LA_BASCULE_PHRASE_1 not in texte
                and TEXTE_DE_LA_BASCULE_PHRASE_2 not in texte
            )

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        for nom_du_module in MODULES_V2:
            html_brut, texte = self.fenetre_de_confirmation(
                nom_du_module, self.configuration_en_memoire([])
            )
            if not textes_de_la_bascule_presents(texte):
                constats_faux.append(
                    f"legacy sans raison, {nom_du_module} : pas de texte"
                )
            if self.attribut_du_bouton_de_confirmation(nom_du_module) not in html_brut:
                constats_faux.append(
                    f"legacy sans raison, {nom_du_module} : pas de bouton"
                )
            if TEXTE_PAS_ENCORE_DISPONIBLE in texte:
                constats_faux.append(
                    f"legacy sans raison, {nom_du_module} : « pas encore disponible »"
                )

        with self.point_de_sauvegarde_annule():
            self.creer_un_asset_legacy("origine")
            self.creer_une_carte_nfc(self.tenant)
            for nom_du_module in MODULES_V2:
                html_brut, texte = self.fenetre_de_confirmation(
                    nom_du_module, self.configuration_en_memoire([])
                )
                textes_attendus = [
                    TEXTE_PAS_ENCORE_DISPONIBLE,
                    RAISON_5_MONNAIE_PROPRE,
                    RAISON_6_CARTES_NFC,
                    TEXTE_CONTACTEZ_NOUS,
                ]
                for texte_attendu in textes_attendus:
                    if texte_attendu not in texte:
                        constats_faux.append(
                            f"legacy retenu, {nom_du_module} : « {texte_attendu} » absent"
                        )
                if self.attribut_du_bouton_de_confirmation(nom_du_module) in html_brut:
                    constats_faux.append(
                        f"legacy retenu, {nom_du_module} : bouton présent"
                    )
                if not textes_de_la_bascule_absents(texte):
                    constats_faux.append(
                        f"legacy retenu, {nom_du_module} : texte de bascule"
                    )

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        for nom_du_module in MODULES_V2:
            html_brut, texte = self.fenetre_de_confirmation(
                nom_du_module, self.configuration_en_memoire([])
            )
            if self.attribut_du_bouton_de_confirmation(nom_du_module) not in html_brut:
                constats_faux.append(f"v2, {nom_du_module} : pas de bouton")
            if not textes_de_la_bascule_absents(texte):
                constats_faux.append(f"v2, {nom_du_module} : texte de bascule")
            if TEXTE_PAS_ENCORE_DISPONIBLE in texte:
                constats_faux.append(f"v2, {nom_du_module} : « pas encore disponible »")

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        html_brut, texte = self.fenetre_de_confirmation(
            "module_adhesion", self.configuration_en_memoire([])
        )
        if self.attribut_du_bouton_de_confirmation("module_adhesion") not in html_brut:
            constats_faux.append("legacy, adhésions : pas de bouton")
        if not textes_de_la_bascule_absents(texte):
            constats_faux.append("legacy, adhésions : texte de bascule")

        assert constats_faux == [], "\n".join(constats_faux)

    def test_fenetre_accessible_fermer_avec_raisons_bouton_desactive_au_clic(self):
        """
        La fenêtre de confirmation d'un module V2 éteint :
        - toujours : le conteneur est une boîte de dialogue accessible (`role="dialog"`,
          `aria-modal="true"`, `aria-labelledby` vers un élément de la fenêtre qui porte
          cet `id`) ;
        - lieu legacy retenu (cartes NFC) : le bloc des raisons est en `role="alert"` ; le
          titre (`<h3>`) est « Module non disponible » ; un seul bouton, « Fermer » (pas
          « Annuler », pas de confirmation) ;
        - lieu legacy sans raison, et lieu v2 : le bouton de confirmation se désactive au
          clic (`hx-disabled-elt="this"`), pour qu'un double clic n'envoie pas deux POST.
        Rendu en français : « Enable module » s'affiche « Activer le module », « Cancel »
        s'affiche « Annuler ».
        / Accessible dialog; with reasons: alert block, "Close" only; the confirm button
        disables itself on click.
        """
        constats_faux = []

        def verifier_la_boite_de_dialogue(html_brut, contexte):
            balise_du_conteneur = re.search(r'<div[^>]*role="dialog"[^>]*>', html_brut)
            if balise_du_conteneur is None:
                constats_faux.append(f"{contexte} : pas de role=dialog")
                return
            if 'aria-modal="true"' not in balise_du_conteneur.group(0):
                constats_faux.append(f"{contexte} : pas d'aria-modal")
            identifiant_du_titre = re.search(
                r'aria-labelledby="([^"]+)"', balise_du_conteneur.group(0)
            )
            if identifiant_du_titre is None:
                constats_faux.append(f"{contexte} : pas d'aria-labelledby")
                return
            if f'id="{identifiant_du_titre.group(1)}"' not in html_brut:
                constats_faux.append(f"{contexte} : aria-labelledby sans cible")

        def balise_du_bouton_de_confirmation(html_brut, nom_du_module):
            attribut = self.attribut_du_bouton_de_confirmation(nom_du_module)
            for balise in re.findall(r"<button[^>]*>", html_brut):
                if attribut in balise:
                    return balise
            return None

        # Lieu legacy retenu. / Legacy venue held by a reason.
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        with self.point_de_sauvegarde_annule():
            self.creer_une_carte_nfc(self.tenant)
            html_brut, texte = self.fenetre_de_confirmation(
                "module_caisse", self.configuration_en_memoire([])
            )
        verifier_la_boite_de_dialogue(html_brut, "legacy retenu")
        if 'role="alert"' not in html_brut:
            constats_faux.append("legacy retenu : bloc des raisons sans role=alert")
        titre_de_la_fenetre = re.search(r"<h3[^>]*>(.*?)</h3>", html_brut, re.DOTALL)
        if titre_de_la_fenetre is None or (
            texte_lisible_du_html(titre_de_la_fenetre.group(1))
            != "Module non disponible"
        ):
            constats_faux.append(
                "legacy retenu : titre autre que « Module non disponible »"
            )
        if "Activer le module" in texte:
            constats_faux.append("legacy retenu : titre « Activer le module »")
        if "Annuler" in texte:
            constats_faux.append("legacy retenu : bouton « Annuler »")
        boutons = re.findall(r"<button[^>]*>.*?</button>", html_brut, re.DOTALL)
        textes_des_boutons = []
        for bouton in boutons:
            textes_des_boutons.append(
                texte_lisible_du_html(re.sub(r"<[^>]+>", " ", bouton))
            )
        if textes_des_boutons != ["Fermer"]:
            constats_faux.append(f"legacy retenu : boutons {textes_des_boutons}")

        # Lieu legacy sans raison, puis lieu v2. / Legacy without reason, then v2.
        for moteur in [MOTEUR_LEGACY, MOTEUR_V2]:
            self.poser_le_moteur_du_lieu_dedie(moteur)
            html_brut, _texte = self.fenetre_de_confirmation(
                "module_caisse", self.configuration_en_memoire([])
            )
            verifier_la_boite_de_dialogue(html_brut, moteur)
            balise = balise_du_bouton_de_confirmation(html_brut, "module_caisse")
            if balise is None:
                constats_faux.append(f"{moteur} : pas de bouton de confirmation")
            elif 'hx-disabled-elt="this"' not in balise:
                constats_faux.append(f"{moteur} : bouton sans hx-disabled-elt")

        assert constats_faux == [], "\n".join(constats_faux)

    # ================================================================== #
    #  15 — La carte du tableau de bord                                   #
    #  / 15 — The dashboard card                                          #
    # ================================================================== #

    def test_carte_du_tableau_de_bord_selon_les_raisons(self):
        """
        Tous les modules éteints, cartes lues dans `dashboard_callback` :
        - lieu legacy sans raison : les quatre cartes V2 (caisse comprise) s'affichent
          comme pour un lieu v2 (interrupteur, encart BETA), SAUF le lien d'ouverture
          (« Open POS », « Open kiosk ») : absent tant que le lieu est legacy, il
          mènerait à un refus. Comparaison : le HTML de la carte v2, privé de son lien
          `<a class="tb-carte-ouvrir">…</a>`, égale le HTML de la carte legacy (espaces
          réduits) ; la carte legacy n'a aucun `tb-carte-ouvrir`. Elles ne sont pas
          fermées (`moteur_legacy` faux) et n'affichent pas la phrase fixe du verrou ;
        - retenu (monnaie propre, cartes NFC) : les quatre cartes restent fermées
          (`moteur_legacy`), sans interrupteur ; leur HTML montre les deux raisons, et pas
          la phrase fixe du verrou.
        / Legacy without reason: V2 cards have a switch; with reasons: closed, no switch,
        reasons shown instead of the fixed sentence.
        """
        phrase_fixe_du_verrou = self.phrase_fixe_du_verrou()
        constats_faux = []

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        cartes_en_v2 = self.cartes_du_tableau_de_bord(self.configuration_en_memoire([]))

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        cartes = self.cartes_du_tableau_de_bord(self.configuration_en_memoire([]))
        for nom_du_module in MODULES_V2:
            carte = cartes[nom_du_module]
            html_brut, texte = self.html_de_la_carte(carte)
            html_en_v2, _texte_en_v2 = self.html_de_la_carte(
                cartes_en_v2[nom_du_module]
            )
            html_en_v2_sans_lien_d_ouverture = re.sub(
                r'<a class="tb-carte-ouvrir".*?</a>', "", html_en_v2, flags=re.DOTALL
            )
            if " ".join(html_brut.split()) != " ".join(
                html_en_v2_sans_lien_d_ouverture.split()
            ):
                constats_faux.append(
                    f"sans raison, {nom_du_module} : HTML différent du v2 (hors lien)"
                )
            if "tb-carte-ouvrir" in html_brut:
                constats_faux.append(
                    f"sans raison, {nom_du_module} : lien d'ouverture affiché"
                )
            if not carte.get("montre_interrupteur"):
                constats_faux.append(
                    f"sans raison, {nom_du_module} : pas d'interrupteur"
                )
            if carte.get("moteur_legacy"):
                constats_faux.append(f"sans raison, {nom_du_module} : carte fermée")
            if 'role="switch"' not in html_brut:
                constats_faux.append(
                    f"sans raison, {nom_du_module} : interrupteur absent"
                )
            if phrase_fixe_du_verrou in texte:
                constats_faux.append(f"sans raison, {nom_du_module} : phrase du verrou")

        with self.point_de_sauvegarde_annule():
            self.creer_un_asset_legacy("origine")
            self.creer_une_carte_nfc(self.tenant)
            cartes = self.cartes_du_tableau_de_bord(self.configuration_en_memoire([]))
            for nom_du_module in MODULES_V2:
                carte = cartes[nom_du_module]
                html_brut, texte = self.html_de_la_carte(carte)
                if carte.get("moteur_legacy") is not True:
                    constats_faux.append(f"retenu, {nom_du_module} : carte pas fermée")
                if carte.get("montre_interrupteur"):
                    constats_faux.append(
                        f"retenu, {nom_du_module} : interrupteur montré"
                    )
                if 'role="switch"' in html_brut:
                    constats_faux.append(
                        f"retenu, {nom_du_module} : interrupteur affiché"
                    )
                textes_attendus_sur_la_carte = [
                    TEXTE_PAS_ENCORE_DISPONIBLE,
                    RAISON_5_MONNAIE_PROPRE,
                    RAISON_6_CARTES_NFC,
                    TEXTE_CONTACTEZ_NOUS,
                ]
                for texte_attendu in textes_attendus_sur_la_carte:
                    if texte_attendu not in texte:
                        constats_faux.append(
                            f"retenu, {nom_du_module} : « {texte_attendu} » absent"
                        )
                if phrase_fixe_du_verrou in texte:
                    constats_faux.append(
                        f"retenu, {nom_du_module} : phrase fixe affichée"
                    )

        assert constats_faux == [], "\n".join(constats_faux)

    def test_carte_retenue_liste_les_raisons(self):
        """
        Lieu legacy retenu par deux raisons (monnaie propre, cartes NFC) : sur chacune des
        4 cartes V2, les raisons sont une liste `<ul>` qui porte un `aria-label` (texte
        non vide), avec une entrée `<li>` par raison, dans l'ordre des raisons.
        / Held venue: each V2 card lists its reasons in a labelled <ul>, one <li> each.
        """
        constats_faux = []
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)

        with self.point_de_sauvegarde_annule():
            self.creer_un_asset_legacy("origine")
            self.creer_une_carte_nfc(self.tenant)
            cartes = self.cartes_du_tableau_de_bord(self.configuration_en_memoire([]))

        for nom_du_module in MODULES_V2:
            html_brut, _texte = self.html_de_la_carte(cartes[nom_du_module])
            liste_des_raisons = re.search(
                r"<ul([^>]*)>(.*?)</ul>", html_brut, re.DOTALL
            )
            if liste_des_raisons is None:
                constats_faux.append(f"{nom_du_module} : pas de liste <ul>")
                continue
            etiquette = re.search(r'aria-label="([^"]*)"', liste_des_raisons.group(1))
            if etiquette is None or not etiquette.group(1).strip():
                constats_faux.append(f"{nom_du_module} : liste sans aria-label")
            entrees = re.findall(
                r"<li[^>]*>(.*?)</li>", liste_des_raisons.group(2), re.DOTALL
            )
            textes_des_entrees = []
            for entree in entrees:
                textes_des_entrees.append(texte_lisible_du_html(entree))
            if textes_des_entrees != [RAISON_5_MONNAIE_PROPRE, RAISON_6_CARTES_NFC]:
                constats_faux.append(f"{nom_du_module} : entrées {textes_des_entrees}")

        assert constats_faux == [], "\n".join(constats_faux)

    def test_carte_legacy_sans_raison_module_allume_sans_lien_d_ouverture(self):
        """
        Lieu legacy sans raison dont les 4 modules V2 sont restés allumés en base : les
        cartes gardent leur interrupteur (pour éteindre, ou pour la bascule), mais aucune
        n'a de lien d'ouverture (« Open POS », « Open kiosk ») tant que le lieu est
        legacy : la caisse V2 et la tireuse refusent un lieu legacy, le lien mènerait à un
        refus.
        Lieu v2 (témoin), mêmes modules : « Open POS » sur la caisse, « Open kiosk » sur la
        tireuse.
        / Legacy venue without reason, V2 modules still on: switches kept, no "Open" link;
        v2 keeps both links.
        """
        constats_faux = []
        configuration_modules_allumes = self.configuration_en_memoire(MODULES_V2)

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        cartes_en_v2 = self.cartes_du_tableau_de_bord(configuration_modules_allumes)
        if cartes_en_v2["module_caisse"].get("lien_externe") != "/laboutik/caisse/":
            constats_faux.append("v2 : « Open POS » absent")
        if cartes_en_v2["module_tireuse"].get("lien_externe") != "/controlvanne/kiosk/":
            constats_faux.append("v2 : « Open kiosk » absent")

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        cartes = self.cartes_du_tableau_de_bord(configuration_modules_allumes)
        for nom_du_module in MODULES_V2:
            carte = cartes[nom_du_module]
            html_brut, _texte = self.html_de_la_carte(carte)
            if not carte.get("montre_interrupteur"):
                constats_faux.append(f"legacy, {nom_du_module} : pas d'interrupteur")
            if carte.get("lien_externe"):
                constats_faux.append(
                    f"legacy, {nom_du_module} : lien {carte.get('lien_externe')}"
                )
            if "tb-carte-ouvrir" in html_brut:
                constats_faux.append(f"legacy, {nom_du_module} : lien dans le HTML")

        assert constats_faux == [], "\n".join(constats_faux)
