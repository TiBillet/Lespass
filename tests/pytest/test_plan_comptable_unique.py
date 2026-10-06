"""
tests/pytest/test_plan_comptable_unique.py
Un seul plan comptable, toujours présent : plan par défaut, chargement, unicité,
bouton de l'admin.
/ One single chart of accounts, always present: default plan, loading, uniqueness,
admin button.

LOCALISATION : tests/pytest/test_plan_comptable_unique.py

CE QUI EST TESTÉ / WHAT IS TESTED
---------------------------------
Fiche : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-E-plan-comptable.md §2, §3.1 à §3.4.

- Le plan par défaut : numéros à 6 chiffres, un compte de TVA par taux, les
  correspondances des moyens de paiement.
- Le chargement (commande `charger_plan_comptable`, bouton de l'admin, filet) AJOUTE ce
  qui manque. Il n'efface rien et ne renumérote rien.
- Le numéro de compte est unique dans un lieu (contrainte en base).
- Les deux migrations de données : dédoublonnage des numéros, chargement du plan dans
  un lieu qui n'a aucun compte.
- Les catégories connues du chargeur (écarts d'encaissement, financement participatif)
  sont reliées à leur compte si elles existent. Le chargeur ne les crée pas.
- Le compte d'un règlement (§3.1) : la monnaie d'abord, le moyen ensuite (seulement
  sans monnaie ou pour la monnaie du lieu), sinon une erreur. Le FED (`SF`) passe
  toujours par sa monnaie, au 467000.
- Le journal (§3.2) : le point de vente gagne ; sinon la table des neuf origines.
- Le compte d'un article (§3.3) : les règles, dans l'ordre de la fiche.
- Le FEC (`comptabilite/fec.py`) lit le plan de la caisse,
  et cherche la TVA par son taux.
- Les écrans pour un bénévole (fiche §4) : le menu « Ventes & comptabilité » mène au
  plan, aux comptes des moyens et aux comptes des monnaies ; le plan est regroupé par
  nature, avec une aide par nature ; l'écran des monnaies liste les monnaies acceptées
  par le lieu ; le code journal est dans le formulaire du point de vente.
- « Plan complet ? » (`ce_qui_manque_pour_exporter`) : ce qui manque pour exporter, et
  son composant en tête des trois écrans du plan. Il relit tout l'historique du lieu :
  il est calculé au clic sur le bouton « Vérifier le plan », jamais à l'ouverture d'un
  écran. Son nombre de requêtes ne grandit pas
  avec le nombre de produits vendus ; les ventes en points n'y comptent pas ; un compte
  du plan par défaut supprimé est nommé.
- Le formulaire du compte d'une monnaie (`MappingMonnaieForm`) : la liste des monnaies,
  les refus.
- Les gardes du service de vente (avoirs), du remboursement Stripe
  (`PaiementStripe/utils.py`) et des règles du plan : chacune par un test court.

SCHÉMA DÉDIÉ : le test lit et vide le plan du lieu. Chaque test tourne dans une
transaction annulée à la fin (`FastTenantTestCase` hérite de `TestCase`) : l'état du
schéma reste celui laissé par les migrations, qui ont chargé le plan par défaut.
/ Dedicated schema: each test runs in a rolled-back transaction; the schema keeps the
state left by the migrations, which loaded the default plan.

Lancement / Run:
    make test ARGS="tests/pytest/test_plan_comptable_unique.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import csv  # noqa: E402
import importlib  # noqa: E402
import re  # noqa: E402
import uuid  # noqa: E402
from datetime import timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from io import StringIO  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

from django.core.exceptions import ValidationError  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import IntegrityError, connection, transaction  # noqa: E402
from django.db.migrations.loader import MigrationLoader  # noqa: E402
from django.db.models import Max, Min  # noqa: E402
from django.test import RequestFactory  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.utils import timezone, translation  # noqa: E402
from django.utils.translation import gettext  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402
from stripe import InvalidRequestError  # noqa: E402

from Administration.admin import dashboard  # noqa: E402
from Administration.admin.laboutik import MappingMonnaieForm  # noqa: E402
from Administration.admin.site import staff_admin_site  # noqa: E402
from AuthBillet.models import TibilletUser, Wallet  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    CategorieProduct,
    Configuration,
    LigneArticle,
    Paiement_stripe,
    PaymentMethod,
    Price,
    PriceSold,
    Product,
    ProductSold,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente  # noqa: E402
from BaseBillet.services_vente import (  # noqa: E402
    NOM_ECART_RECU_EN_MOINS,
    NOM_ECART_RECU_EN_PLUS,
    NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE,
    ajouter_article,
    ajouter_l_article_d_avoir,
    ajouter_reglement,
    ecrire_la_vente_d_avoir_d_une_ligne,
    encaisser_vente,
    ouvrir_vente,
    tarif_vendu_d_ecart_d_encaissement,
)
from comptabilite.fec import generer_fec_cloture  # noqa: E402
from comptabilite.models import ClotureCaisse  # noqa: E402
from crowds.views import _get_or_create_crowdfunding_price  # noqa: E402
from Customers.models import Client  # noqa: E402
from fabriques_panier import (  # noqa: E402
    configuration_modifiee,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_ecran import (  # noqa: E402
    LecteurDesLiens,
    attributs_des_elements,
    texte_sans_espaces_en_trop,
    textes_des_elements,
)
from fabriques_vente import creer_tarif_vendu, verifier_egalites  # noqa: E402
from fedow_connect.models import FedowConfig  # noqa: E402
from fedow_core.models import Asset  # noqa: E402
from fedow_public.models import AssetFedowPublic  # noqa: E402
from laboutik.models import (  # noqa: E402
    CartePrimaire,
    CompteComptable,
    LaboutikConfiguration,
    MappingMonnaie,
    MappingMoyenDePaiement,
    PointDeVente,
)
from laboutik.plan_comptable import (  # noqa: E402
    CompteComptableManquant,
    charger_le_plan_comptable_par_defaut,
    code_journal_du_point_de_vente,
    collisions_de_codes_journal,
    compte_des_ventes_reglees_en_jetons,
    compte_pour_article,
    compte_pour_reglement,
    journal_pour,
    nom_de_la_monnaie,
    s_assurer_que_le_plan_existe,
)
from PaiementStripe.utils import partial_refund_payment  # noqa: E402
from QrcodeCashless.models import CarteCashless  # noqa: E402
from laboutik.plan_comptable_par_defaut import (  # noqa: E402
    NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF,
)


# --------------------------------------------------------------------------- #
#  Le plan attendu (fiche E §3.4), recopié ici à la main.                      #
#  The expected plan (sheet E §3.4), copied here by hand.                      #
# --------------------------------------------------------------------------- #
# Le test ne lit PAS le module de données du plan : il compare le plan chargé à la
# fiche. Lire le module rendrait le test toujours vrai.
# / The test does NOT read the plan's data module: it compares the loaded plan with
# the sheet. Reading the module would make the test always true.

NATURE_ATTENDUE_PAR_NUMERO = {
    # Ventes / Sales
    "706000": CompteComptable.VENTE,
    "707000": CompteComptable.VENTE,
    "707900": CompteComptable.VENTE,
    "756000": CompteComptable.VENTE,
    "754000": CompteComptable.VENTE,
    # TVA collectée / Collected VAT
    "445711": CompteComptable.TVA,
    "445712": CompteComptable.TVA,
    "445713": CompteComptable.TVA,
    "445714": CompteComptable.TVA,
    # Trésorerie / Treasury
    "530000": CompteComptable.TRESORERIE,
    "511200": CompteComptable.TRESORERIE,
    "512100": CompteComptable.TRESORERIE,
    "517100": CompteComptable.TRESORERIE,
    "512000": CompteComptable.TRESORERIE,
    # Tiers (467000 : le compte de la monnaie FED, pas d'un moyen)
    # / Third parties (467000: the FED currency's account, not a method's)
    "467000": CompteComptable.TIERS,
    "419100": CompteComptable.TIERS,
    "471000": CompteComptable.TIERS,
    # Charges / Expenses
    "623400": CompteComptable.CHARGE,
    # Écarts d'encaissement / Collection gaps
    "758000": CompteComptable.PRODUIT_EXCEPTIONNEL,
    "658000": CompteComptable.CHARGE,
}

NUMEROS_DU_PLAN_PAR_DEFAUT = set(NATURE_ATTENDUE_PAR_NUMERO.keys())

# Un seul compte de TVA par taux. Il est toujours cherché par son taux.
# / One VAT account per rate, always looked up by its rate.
NUMERO_DE_TVA_ATTENDU_PAR_TAUX = {
    Decimal("20.00"): "445711",
    Decimal("10.00"): "445712",
    Decimal("5.50"): "445713",
    Decimal("2.10"): "445714",
}

# Correspondances des moyens de paiement. NA, NM, SF et QR n'en ont aucune.
# / Payment method mappings. NA, NM, SF and QR have none.
COMPTE_ATTENDU_PAR_MOYEN = {
    "CA": "530000",
    "CH": "511200",
    "CC": "512100",
    "SN": "517100",
    "SP": "517100",
    "SR": "517100",
    "TR": "512000",
    "LE": "419100",
    "LG": "419100",
    "UK": "471000",
}
MOYENS_SANS_CORRESPONDANCE = ["NA", "NM", "SF", "QR"]

# La migration de données qui prépare chaque lieu, et ses fonctions.
# / The data migration that prepares each venue, and its functions.
MIGRATION_DE_CHARGEMENT = "0002_preparer_chaque_lieu"
FONCTION_DE_CHARGEMENT = "charger_le_plan_si_aucun_compte"
MIGRATION_DU_FED = "0002_preparer_chaque_lieu"
FONCTION_DE_LA_MIGRATION_DU_FED = "relier_le_fed_au_compte_du_reseau"
MIGRATION_DES_CROWDS = "0002_preparer_chaque_lieu"
FONCTION_DE_LA_MIGRATION_DES_CROWDS = (
    "ranger_les_crowds_dans_le_financement_participatif"
)

# Le journal d'une vente sans point de vente, selon son origine (fiche §3.2).
# / The journal of a sale without point of sale, by origin (sheet §3.2).
JOURNAL_ATTENDU_PAR_ORIGINE = {
    "LB": "CAISSE",
    "QR": "CAISSE",
    "NF": "CAISSE",
    "TI": "TIREUSE",
    "LP": "WEB",
    "AP": "WEB",
    "EX": "WEB",
    "WK": "WEB",
    "AD": "ADMIN",
}

# Le compte d'un article selon son type de produit, sans catégorie de caisse ni mode
# de caisse (fiche §3.3, règle 4).
# / An item's account by product type, without POS category or POS method (rule 4).
COMPTE_ATTENDU_PAR_TYPE_DE_PRODUIT = {
    Product.BILLET: "706000",
    Product.FREERES: "706000",
    Product.BADGE: "706000",
    Product.QRCODE_MA: "706000",
    Product.RESOURCE: "706000",
    Product.ADHESION: "756000",
}


# --------------------------------------------------------------------------- #
#  Utilitaires (hors de la classe) / Helpers (outside the class)              #
# --------------------------------------------------------------------------- #


def _vider_le_plan_du_lieu():
    """
    Supprime toutes les correspondances (moyens et monnaies) et tous les comptes du
    lieu courant. Les catégories reliées passent à vide (SET_NULL). Les
    correspondances des monnaies d'abord : elles protègent leur compte (PROTECT).
    / Deletes every mapping (methods and currencies) and account of the current venue.
    Currency mappings first: they protect their account.
    """
    MappingMonnaie.objects.all().delete()
    MappingMoyenDePaiement.objects.all().delete()
    CompteComptable.objects.all().delete()


def _charger_le_plan_par_la_commande(nom_du_schema):
    """
    Lance la commande `charger_plan_comptable` sur le lieu, sans profil.
    / Runs the `charger_plan_comptable` command on the venue, without profile.
    """
    call_command(
        "charger_plan_comptable",
        schema=nom_du_schema,
        stdout=StringIO(),
        stderr=StringIO(),
    )


def _lancer_la_fonction_de_migration(nom_de_la_migration, nom_de_la_fonction):
    """
    Appelle la fonction `RunPython` d'une migration de `laboutik`, comme le ferait
    `migrate_schemas` : avec les modèles historiques de l'état juste avant cette
    migration, et un vrai `schema_editor` du lieu courant.
    / Calls a `laboutik` migration's RunPython function as `migrate_schemas` would:
    historical models of the state just before it, and a real schema_editor.
    """
    module_de_la_migration = importlib.import_module(
        f"laboutik.migrations.{nom_de_la_migration}"
    )
    fonction_de_la_migration = getattr(module_de_la_migration, nom_de_la_fonction)

    chargeur_des_migrations = MigrationLoader(connection)
    etat_avant_la_migration = chargeur_des_migrations.project_state(
        ("laboutik", nom_de_la_migration), at_end=False
    )
    with connection.schema_editor() as editeur_de_schema:
        fonction_de_la_migration(etat_avant_la_migration.apps, editeur_de_schema)


def _compte(numero_de_compte):
    """
    Le compte du lieu courant qui porte ce numéro.
    / The current venue's account with this number.
    """
    return CompteComptable.objects.get(numero_de_compte=numero_de_compte)


def _creer_un_compte(numero_de_compte, libelle, nature):
    """
    Crée un compte ajouté par le lieu, hors du plan par défaut.
    / Creates a venue-added account, outside the default plan.
    """
    return CompteComptable.objects.create(
        numero_de_compte=numero_de_compte,
        libelle_du_compte=libelle,
        nature_du_compte=nature,
    )


def _portefeuille_d_origine():
    """
    Un portefeuille d'origine pour une monnaie de test (champ obligatoire).
    / An origin wallet for a test currency (mandatory field).
    """
    return Wallet.objects.create(name=f"Portefeuille plan unique {identifiant_unique()}")


def _monnaie_fedow_core(lieu_d_origine, categorie=Asset.TLF):
    """
    Une monnaie du moteur fedow_core, créée par `lieu_d_origine`.
    / A fedow_core currency, created by `lieu_d_origine`.
    """
    return Asset.objects.create(
        name=f"Monnaie plan unique {identifiant_unique()}",
        currency_code="EUR",
        category=categorie,
        tenant_origin=lieu_d_origine,
        wallet_origin=_portefeuille_d_origine(),
    )


def _monnaie_ancien_fedow(lieu_d_origine, categorie=AssetFedowPublic.TOKEN_LOCAL_FIAT):
    """
    Une monnaie de l'ancien Fedow (`fedow_public.AssetFedowPublic`), créée par
    `lieu_d_origine`.
    / An old-Fedow currency, created by `lieu_d_origine`.
    """
    return AssetFedowPublic.objects.create(
        name=f"Monnaie ancien Fedow plan unique {identifiant_unique()}",
        currency_code="EUR",
        category=categorie,
        origin=lieu_d_origine,
        wallet_origin=_portefeuille_d_origine(),
    )


def _un_autre_lieu():
    """
    Un lieu qui n'est pas le lieu du test : le lieu `public`, qui existe toujours.
    Créer un vrai lieu créerait un schéma et rejouerait toutes les migrations.
    / A venue other than the test venue: the `public` one, which always exists.
    """
    return Client.objects.get(schema_name="public")


def _ranger_dans_une_categorie(tarif_vendu, compte):
    """
    Range le produit du tarif vendu dans une nouvelle catégorie de caisse, reliée à
    `compte`.
    / Puts the sold price's product in a new POS category, linked to `compte`.
    """
    categorie = CategorieProduct.objects.create(
        name=f"Catégorie plan unique {identifiant_unique()}",
        compte_comptable=compte,
    )
    produit = tarif_vendu.productsold.product
    produit.categorie_pos = categorie
    produit.save()
    return categorie


def _ligne_d_article(tarif_vendu, hors_chiffre_affaires=False, asset=None):
    """
    Une ligne d'article NON enregistrée : `compte_pour_article` ne lit que la ligne et
    son produit. `hors_chiffre_affaires` est posé comme le service de vente le fige
    (`BaseBillet/services_vente.py`, `ajouter_article`, étape 4).
    / An UNSAVED item line: compte_pour_article only reads the line and its product.
    `hors_chiffre_affaires` is set the way the sale service freezes it.
    """
    return LigneArticle(
        pricesold=tarif_vendu,
        qty=Decimal("1"),
        amount=500,
        hors_chiffre_affaires=hors_chiffre_affaires,
        asset=asset,
    )


def _point_de_vente(nom, code_journal=""):
    """
    Un point de vente caché (PIEGES 9.41), avec ou sans code journal.
    / A hidden point of sale (PIEGES 9.41), with or without journal code.
    """
    return PointDeVente.objects.create(
        name=nom,
        code_journal=code_journal,
        hidden=True,
    )


def _cloture_j_des_ventes_du_test():
    """
    Une clôture J du lieu courant qui couvre toutes ses ventes réglées (sa plage de
    numéros), écrite à la main : le FEC ne lit que la plage et le fuseau figé dans
    l'en-tête du rapport.
    / A J closure covering all settled sales, written by hand: the FEC only reads the
    range and the frozen time zone.
    """
    numeros_des_ventes = Vente.objects.filter(statut=Vente.Statut.REGLEE).aggregate(
        premier_numero=Min("numero"), dernier_numero=Max("numero")
    )
    fin_de_la_periode = timezone.now() + timedelta(minutes=1)
    return ClotureCaisse.objects.create(
        niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        numero_sequentiel=990001,
        datetime_debut=fin_de_la_periode - timedelta(days=1),
        datetime_fin=fin_de_la_periode,
        numero_premiere_vente=numeros_des_ventes["premier_numero"],
        numero_derniere_vente=numeros_des_ventes["dernier_numero"],
        rapport_json={"en_tete": {"fuseau_horaire": "Europe/Paris"}},
    )


def _lignes_du_fec(cloture):
    """
    Génère le FEC de la clôture et rend ses lignes (dict par colonne).
    / Generates the closure's FEC and returns its rows.
    """
    contenu_en_octets, _nom, _type = generer_fec_cloture(cloture)
    contenu = contenu_en_octets.decode("utf-8")
    lecteur = csv.DictReader(StringIO(contenu), delimiter="\t")
    lignes_du_fec = []
    for ligne in lecteur:
        lignes_du_fec.append(ligne)
    return lignes_du_fec


# --------------------------------------------------------------------------- #
#  Utilitaires des écrans et de « Plan complet ? » (fiche §4)                  #
#  Helpers for the screens and "Complete plan?" (sheet §4)                    #
# --------------------------------------------------------------------------- #

# Le message vert de « Plan complet ? » quand rien ne manque (brief E-2, règle 5).
# / The green message of "Complete plan?" when nothing is missing.
MESSAGE_DU_PLAN_COMPLET = "Le plan est complet : l'export est possible"

# La phrase orange d'une monnaie sans compte (fiche §4).
# / The orange sentence of a currency without account.
PHRASE_D_UNE_MONNAIE_SANS_COMPTE = (
    "l'export comptable sera refusé tant que ce compte manque"
)

# Les trois écrans du plan, en tête desquels « Plan complet ? » s'affiche.
# / The three plan screens, topped by "Complete plan?".
NOMS_DES_TROIS_ECRANS_DU_PLAN = [
    "staff_admin:laboutik_comptecomptable_changelist",
    "staff_admin:laboutik_mappingmoyendepaiement_changelist",
    "staff_admin:laboutik_mappingmonnaie_changelist",
]


def _ce_qui_manque_pour_exporter():
    """
    Appelle « Plan complet ? » du module du plan comptable.
    / Calls "Complete plan?" from the chart of accounts module.

    L'import est fait ici, à l'appel : si la fonction manque, seuls les tests qui
    l'appellent tombent, les autres tests du fichier tournent.
    / Imported at call time: if the function is missing, only the tests calling it fail.

    :return: la liste des manques ; chaque manque est un dict
        {"phrase": texte FALC, "lien": URL de l'écran qui le règle}
    """
    from laboutik.plan_comptable import ce_qui_manque_pour_exporter

    return ce_qui_manque_pour_exporter()


def _preparer_la_caisse():
    """
    Le singleton de la caisse doit exister en base : il porte la clé de l'empreinte
    des ventes (PIEGES 9.86).
    / The register singleton must exist in the database: it holds the sale HMAC key.
    """
    LaboutikConfiguration.get_solo().save()


def _vendre(tarif_vendu, moyen="CA", asset=None, taux_tva="20", point_de_vente=None):
    """
    Une vente RÉGLÉE d'un article à 5 €, payée en un seul règlement, écrite par le
    service de vente.
    / A SETTLED sale of one 5 € item, paid in one payment, written by the sale service.

    :param tarif_vendu: le `PriceSold` de l'article
    :param moyen: code `PaymentMethod` du règlement
    :param asset: uuid de la monnaie du règlement, ou None
    :param taux_tva: taux de TVA de la ligne, en pour cent (texte)
    :param point_de_vente: `PointDeVente` de la vente, ou None
    :return: la vente réglée
    """
    vente = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.VENTE,
        point_de_vente=point_de_vente,
    )
    ajouter_article(
        vente,
        pricesold=tarif_vendu,
        quantite=Decimal("1"),
        prix_unitaire=500,
        taux_tva=Decimal(taux_tva),
    )
    ajouter_reglement(vente, moyen=moyen, montant=500, asset=asset)
    return encaisser_vente(vente)


def _biere_rangee_au_bar():
    """
    Une bière rangée dans une catégorie reliée au 707000 : elle a un compte.
    / A beer in a category linked to 707000: it has an account.
    """
    biere = creer_tarif_vendu(nom="Bière du bar", methode_caisse=Product.VENTE)
    _ranger_dans_une_categorie(biere, _compte("707000"))
    return biere


def _monnaie_ancien_fedow_d_un_autre_lieu_acceptee_ici(lieu_du_test):
    """
    Une monnaie de l'ancien Fedow créée par un autre lieu et fédérée avec le lieu du
    test : le lieu l'accepte.
    / An old-Fedow currency created by another venue and federated with the test venue.
    """
    monnaie = _monnaie_ancien_fedow(_un_autre_lieu())
    monnaie.federated_with.add(lieu_du_test)
    return monnaie


def _navigateur_d_un_admin_du_lieu(lieu):
    """
    Un navigateur connecté avec un administrateur du lieu.
    / A browser logged in as a venue admin.
    """
    administrateur, _cree = TibilletUser.objects.get_or_create(
        email="admin-plan-unique-ecrans@tibillet.localhost",
        defaults={
            "username": "admin-plan-unique-ecrans@tibillet.localhost",
            "is_staff": True,
            "is_active": True,
        },
    )
    administrateur.client_admin.add(lieu)
    navigateur = TenantClient(lieu)
    navigateur.force_login(administrateur)
    return navigateur, administrateur


def _verdict_du_bouton_verifier_le_plan(navigateur, contenu_de_l_ecran):
    """
    Clique le bouton « Vérifier le plan » d'un écran du plan, comme HTMX le fait : lit
    son adresse (`hx-get`), la demande avec l'en-tête `HX-Request`, et rend le HTML
    reçu (le verdict de « Plan complet ? »).
    / Clicks the "Check the plan" button like HTMX does: reads its hx-get address,
    requests it with the HX-Request header, returns the received HTML (the verdict).
    """
    boutons = attributs_des_elements(contenu_de_l_ecran, "plan-complet-verifier")
    assert len(boutons) == 1, boutons
    adresse_du_verdict = boutons[0].get("hx-get")
    assert adresse_du_verdict, boutons[0]

    reponse_du_verdict = navigateur.get(adresse_du_verdict, HTTP_HX_REQUEST="true")

    assert reponse_du_verdict.status_code == 200, adresse_du_verdict
    return reponse_du_verdict.content.decode()


def _phrases_des_manques(manques):
    """
    Les phrases des manques de « Plan complet ? ».
    / The sentences of the "Complete plan?" missing items.
    """
    phrases = []
    for manque in manques:
        phrases.append(manque["phrase"])
    return phrases


def _noms_accessibles_des_liens_des_manques(contenu_html):
    """
    Le nom que lit un lecteur d'écran pour chaque lien placé DANS un manque de « Plan
    complet ? » (`data-testid="plan-complet-manque"`) : son `aria-label` s'il en a un,
    sinon son texte (texte caché `visually-hidden` compris). Le menu latéral a aussi
    des liens vers les mêmes écrans : il n'est pas lu.
    / The name a screen reader reads for each link INSIDE a "Complete plan?" missing
    item: its aria-label, else its text. The sidebar links are not read.
    """
    elements_des_manques = re.findall(
        r'<li[^>]*data-testid="plan-complet-manque".*?</li>', contenu_html, re.DOTALL
    )
    noms_accessibles = []
    for element_du_manque in elements_des_manques:
        lecteur = LecteurDesLiens()
        lecteur.feed(element_du_manque)
        lecteur.close()
        for lien in lecteur.liens:
            if lien["aria_label"]:
                noms_accessibles.append(texte_sans_espaces_en_trop(lien["aria_label"]))
            else:
                noms_accessibles.append(lien["texte"])
    return noms_accessibles


def _vendre_payee_en_jetons(tarif_vendu, jetons_cadeau):
    """
    Une vente RÉGLÉE d'un article à 5 € payé en jetons cadeau : la ligne porte le moyen
    historique LG, la monnaie, le taux du produit (20 %) et sa part payée en jetons
    (500, hors TVA, D8 bis : TVA 0), comme la caisse l'écrit.
    / A SETTLED sale of one 5 € item paid in gift tokens (LG line, product rate, token
    part 500).
    """
    vente = ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE)
    ajouter_article(
        vente,
        pricesold=tarif_vendu,
        quantite=Decimal("1"),
        prix_unitaire=500,
        taux_tva=Decimal("20"),
        part_en_jetons=500,
        payment_method=PaymentMethod.LOCAL_GIFT,
        asset=jetons_cadeau.uuid,
    )
    ajouter_reglement(
        vente, moyen=PaymentMethod.LOCAL_GIFT, montant=500, asset=jetons_cadeau.uuid
    )
    return encaisser_vente(vente)


def _vente_en_ligne_ouverte_avec_son_paiement_stripe():
    """
    Une vente en ligne EN ATTENTE et son paiement Stripe VALID (moyen « Stripe »,
    `SN`), relié à la vente. Le test y ajoute ses articles, puis l'encaisse.
    `create()` direct du paiement : aucune transition de la machine à états.
    / An open online sale and its VALID Stripe payment. The test adds its items.
    """
    acheteur = creer_utilisateur()
    vente_en_ligne = ouvrir_vente(
        origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur
    )
    paiement = Paiement_stripe.objects.create(
        user=acheteur,
        status=Paiement_stripe.VALID,
        moyen=PaymentMethod.STRIPE_NOFED,
        payment_intent_id=f"pi_test_{identifiant_unique()}",
        vente=vente_en_ligne,
    )
    return SimpleNamespace(vente=vente_en_ligne, paiement=paiement)


def _vendre_en_ligne_un_article_paye_par_stripe(quantite=2, prix_unitaire=1000):
    """
    Une vente en ligne RÉGLÉE : un article payé par Stripe (ligne VALID reliée au
    paiement, règlement Stripe du même montant). Rend la ligne et le paiement.
    / A SETTLED online sale: one item paid by Stripe. Returns the line and payment.
    """
    vente_et_paiement = _vente_en_ligne_ouverte_avec_son_paiement_stripe()
    tarif_vendu = creer_tarif_vendu(nom="Entrée en ligne", prix_en_euros="10.00")
    ligne = ajouter_article(
        vente_et_paiement.vente,
        pricesold=tarif_vendu,
        quantite=Decimal(quantite),
        prix_unitaire=prix_unitaire,
        taux_tva=Decimal("20"),
        payment_method=PaymentMethod.STRIPE_NOFED,
        paiement_stripe=vente_et_paiement.paiement,
        status=LigneArticle.VALID,
    )
    ajouter_reglement(
        vente_et_paiement.vente,
        moyen=PaymentMethod.STRIPE_NOFED,
        montant=ligne.total_ttc,
        paiement_stripe=vente_et_paiement.paiement,
    )
    encaisser_vente(vente_et_paiement.vente)
    return SimpleNamespace(ligne=ligne, paiement=vente_et_paiement.paiement)


def _rembourser_comme_stripe(**arguments_du_remboursement):
    """
    Remplace `stripe.Refund.create` : un remboursement réussi, avec un identifiant et
    le montant demandé (centimes entiers). Un `MagicMock` ne convient pas :
    `int(MagicMock())` vaut 1, sans erreur.
    / Replaces stripe.Refund.create: a successful refund of the amount asked.
    """
    return SimpleNamespace(
        id=f"re_test_{identifiant_unique()}",
        amount=arguments_du_remboursement["amount"],
        status="succeeded",
    )


def _configuration_stripe_du_test():
    """
    La configuration passée au remboursement : seul son compte Stripe Connect est lu.
    Un faux : la vraie `Configuration` du lieu de test créerait un compte chez Stripe.
    / The configuration given to the refund: only its Connect account is read.
    """
    configuration = MagicMock()
    configuration.get_stripe_connect_account.return_value = "acct_test_plan_unique"
    return configuration


def _ventes_avoir_du_paiement(paiement):
    """Les ventes AVOIR qui rendent une ligne de ce paiement Stripe.
    / The AVOIR sales giving back a line of this Stripe payment."""
    return Vente.objects.filter(
        nature=Vente.Nature.AVOIR,
        articles__paiement_stripe=paiement,
    ).distinct()


def _moyens_et_montants(vente):
    """Les règlements d'une vente, relus en base : liste triée (moyen, montant).
    / A sale's payments, read back: sorted (method, amount)."""
    moyens_et_montants = []
    for reglement in Reglement.objects.filter(vente=vente):
        moyens_et_montants.append((reglement.moyen, reglement.montant))
    return sorted(moyens_et_montants)


class TestPlanComptableUnique(FastTenantTestCase):
    """Un seul plan comptable, toujours présent, jamais effacé par un rechargement.
    / One single chart of accounts, always present, never erased by a reload."""

    @classmethod
    def get_test_schema_name(cls):
        return "test_plan_comptable_unique"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-plan-comptable-unique.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test plan comptable unique"

    def setUp(self):
        # La transaction du test precedent a ete annulee : on se replace sur le lieu.
        # Rien d'autre ici : un test qui retire une contrainte doit le faire avant
        # toute ecriture (PIEGES 9.113).
        # / Back on the venue. Nothing else here: a test that drops a constraint
        # must do it before any write.
        connection.set_tenant(self.tenant)

    # ------------------------------------------------------------------ #
    #  Le plan par défaut / The default plan                              #
    # ------------------------------------------------------------------ #

    def test_plan_par_defaut_complet_six_chiffres(self):
        """La migration a chargé le plan de la fiche §3.4 dans le lieu de test.
        / The migration loaded the §3.4 plan into the test venue."""
        numeros_presents = set(
            CompteComptable.objects.values_list("numero_de_compte", flat=True)
        )
        assert numeros_presents == NUMEROS_DU_PLAN_PAR_DEFAUT

        # Chaque numéro a 6 chiffres, chaque compte a un libellé.
        # / Every number has 6 digits, every account has a label.
        for compte in CompteComptable.objects.all():
            assert len(compte.numero_de_compte) == 6, compte.numero_de_compte
            assert compte.numero_de_compte.isdigit(), compte.numero_de_compte
            assert compte.libelle_du_compte.strip() != "", compte.numero_de_compte

        # La nature de chaque compte.
        # / Each account's nature.
        for numero, nature_attendue in NATURE_ATTENDUE_PAR_NUMERO.items():
            compte = CompteComptable.objects.get(numero_de_compte=numero)
            assert compte.nature_du_compte == nature_attendue, numero

        # La TVA, cherchée par taux : un seul compte par taux, au bon numéro.
        # / VAT, looked up by rate: one account per rate, with the right number.
        for taux, numero_attendu in NUMERO_DE_TVA_ATTENDU_PAR_TAUX.items():
            comptes_de_ce_taux = CompteComptable.objects.filter(
                nature_du_compte=CompteComptable.TVA, taux_de_tva=taux
            )
            assert comptes_de_ce_taux.count() == 1, taux
            assert comptes_de_ce_taux.get().numero_de_compte == numero_attendu

        # Les ventes réglées en jetons offerts sont hors TVA (D8 bis).
        # / Sales paid with gifted tokens carry no VAT.
        compte_des_ventes_en_jetons = CompteComptable.objects.get(
            numero_de_compte="707900"
        )
        assert compte_des_ventes_en_jetons.taux_de_tva == Decimal("0.00")

        # Les correspondances des moyens de paiement.
        # / The payment method mappings.
        moyens_presents = set(
            MappingMoyenDePaiement.objects.values_list("moyen_de_paiement", flat=True)
        )
        assert moyens_presents == set(COMPTE_ATTENDU_PAR_MOYEN.keys())
        for moyen, numero_attendu in COMPTE_ATTENDU_PAR_MOYEN.items():
            correspondance = MappingMoyenDePaiement.objects.get(moyen_de_paiement=moyen)
            assert correspondance.compte_de_tresorerie is not None, moyen
            assert (
                correspondance.compte_de_tresorerie.numero_de_compte == numero_attendu
            ), moyen
        for moyen in MOYENS_SANS_CORRESPONDANCE:
            assert not MappingMoyenDePaiement.objects.filter(
                moyen_de_paiement=moyen
            ).exists(), moyen

    # ------------------------------------------------------------------ #
    #  Le chargement ajoute ce qui manque / Loading adds what is missing   #
    # ------------------------------------------------------------------ #

    def test_chargement_ajoute_ce_qui_manque_sans_rien_effacer(self):
        """Un compte modifié, un compte du lieu, une catégorie reliée et une
        correspondance changée gardent leur état ; les manquants sont ajoutés.
        / A modified account, a venue account, a linked category and a changed
        mapping keep their state; the missing ones are added."""
        _vider_le_plan_du_lieu()

        # Un compte du plan, au libellé modifié par le lieu, relié à une catégorie.
        # / A plan account, label changed by the venue, linked to a category.
        compte_du_bar = CompteComptable.objects.create(
            numero_de_compte="707000",
            libelle_du_compte="Ventes du bar (libellé du lieu)",
            nature_du_compte=CompteComptable.VENTE,
        )
        categorie_du_bar = CategorieProduct.objects.create(
            name="Bières plan unique", compte_comptable=compte_du_bar
        )

        # Un compte ajouté par le lieu, hors plan, relié à une autre catégorie.
        # / A venue-added account, outside the plan, linked to another category.
        compte_du_lieu = CompteComptable.objects.create(
            numero_de_compte="706100",
            libelle_du_compte="Billetterie du lieu",
            nature_du_compte=CompteComptable.VENTE,
        )
        categorie_billetterie = CategorieProduct.objects.create(
            name="Billetterie plan unique", compte_comptable=compte_du_lieu
        )

        # La carte bancaire envoyée par le lieu vers son propre compte.
        # / Card payments sent by the venue to its own account.
        compte_du_tpe_du_lieu = CompteComptable.objects.create(
            numero_de_compte="512150",
            libelle_du_compte="TPE du lieu",
            nature_du_compte=CompteComptable.TRESORERIE,
        )
        correspondance_carte = MappingMoyenDePaiement.objects.create(
            moyen_de_paiement="CC",
            libelle_moyen="Carte du lieu",
            compte_de_tresorerie=compte_du_tpe_du_lieu,
        )

        _charger_le_plan_par_la_commande(self.tenant.schema_name)

        # Rien n'est effacé ni renuméroté.
        # / Nothing is erased or renumbered.
        compte_du_bar.refresh_from_db()
        assert compte_du_bar.numero_de_compte == "707000"
        assert compte_du_bar.libelle_du_compte == "Ventes du bar (libellé du lieu)"
        assert CompteComptable.objects.filter(numero_de_compte="707000").count() == 1
        categorie_du_bar.refresh_from_db()
        assert categorie_du_bar.compte_comptable_id == compte_du_bar.uuid

        assert CompteComptable.objects.filter(uuid=compte_du_lieu.uuid).exists()
        categorie_billetterie.refresh_from_db()
        assert categorie_billetterie.compte_comptable_id == compte_du_lieu.uuid

        correspondance_carte.refresh_from_db()
        assert (
            correspondance_carte.compte_de_tresorerie_id == compte_du_tpe_du_lieu.uuid
        )

        # Ce qui manquait est ajouté : tout le plan, et la correspondance des espèces.
        # / What was missing is added: the whole plan, and the cash mapping.
        numeros_presents = set(
            CompteComptable.objects.values_list("numero_de_compte", flat=True)
        )
        assert numeros_presents == NUMEROS_DU_PLAN_PAR_DEFAUT | {"706100", "512150"}
        correspondance_especes = MappingMoyenDePaiement.objects.get(
            moyen_de_paiement="CA"
        )
        assert correspondance_especes.compte_de_tresorerie.numero_de_compte == "530000"

    def test_chargement_cherche_la_tva_par_taux(self):
        """Un compte de TVA à 20 % au numéro du lieu suffit : le chargement n'en
        crée pas un second au numéro du plan.
        / A 20 % VAT account with the venue's number is enough: loading does not
        create a second one with the plan's number."""
        _vider_le_plan_du_lieu()
        compte_de_tva_du_lieu = CompteComptable.objects.create(
            numero_de_compte="445700",
            libelle_du_compte="TVA collectée 20 % (numéro du lieu)",
            nature_du_compte=CompteComptable.TVA,
            taux_de_tva=Decimal("20.00"),
        )

        _charger_le_plan_par_la_commande(self.tenant.schema_name)

        comptes_de_tva_a_vingt = CompteComptable.objects.filter(
            nature_du_compte=CompteComptable.TVA, taux_de_tva=Decimal("20.00")
        )
        assert list(comptes_de_tva_a_vingt) == [compte_de_tva_du_lieu]
        assert not CompteComptable.objects.filter(numero_de_compte="445711").exists()

        # Les autres taux, absents, sont ajoutés au numéro du plan.
        # / The other rates, missing, are added with the plan's number.
        for taux in [Decimal("10.00"), Decimal("5.50"), Decimal("2.10")]:
            compte_de_ce_taux = CompteComptable.objects.get(
                nature_du_compte=CompteComptable.TVA, taux_de_tva=taux
            )
            assert (
                compte_de_ce_taux.numero_de_compte
                == NUMERO_DE_TVA_ATTENDU_PAR_TAUX[taux]
            )

    def test_chargement_tva_numero_pris_par_un_autre_taux_avertit(self):
        """Le lieu a 445712 à 20 % : le compte à 10 % (445712 au plan) n'est ni créé
        ni écrasé ; le chargement avertit et ne casse pas.
        / The venue has 445712 at 20 %: the 10 % account (445712 in the plan) is
        neither created nor overwritten; loading warns and does not fail."""
        _vider_le_plan_du_lieu()
        compte_de_tva_du_lieu = CompteComptable.objects.create(
            numero_de_compte="445712",
            libelle_du_compte="TVA collectée 20 % (ancien numéro du lieu)",
            nature_du_compte=CompteComptable.TVA,
            taux_de_tva=Decimal("20.00"),
        )

        avertissements = charger_le_plan_comptable_par_defaut()

        compte_de_tva_du_lieu.refresh_from_db()
        assert compte_de_tva_du_lieu.taux_de_tva == Decimal("20.00")
        assert not CompteComptable.objects.filter(
            nature_du_compte=CompteComptable.TVA, taux_de_tva=Decimal("10.00")
        ).exists()
        assert len(avertissements) == 1
        assert "445712" in avertissements[0]

    def test_bouton_de_l_admin_n_efface_plus_le_plan(self):
        """Le bouton « Charger le plan » de l'admin ajoute ce qui manque. Le compte
        existant et le lien de la catégorie restent.
        / The admin "Load the plan" button adds what is missing. The existing account
        and the category link remain."""
        _vider_le_plan_du_lieu()
        compte_du_bar = CompteComptable.objects.create(
            numero_de_compte="707000",
            libelle_du_compte="Ventes du bar (libellé du lieu)",
            nature_du_compte=CompteComptable.VENTE,
        )
        categorie_du_bar = CategorieProduct.objects.create(
            name="Bières bouton plan unique", compte_comptable=compte_du_bar
        )

        # Les routes de la caisse exigent le module caisse et un admin du lieu.
        # / Register routes require the register module and a venue admin.
        configuration = Configuration.get_solo()
        configuration.module_caisse = True
        configuration.save()
        administrateur, _cree = TibilletUser.objects.get_or_create(
            email="admin-plan-unique@tibillet.localhost",
            defaults={
                "username": "admin-plan-unique@tibillet.localhost",
                "is_staff": True,
                "is_active": True,
            },
        )
        administrateur.client_admin.add(self.tenant)
        navigateur = TenantClient(self.tenant)
        navigateur.force_login(administrateur)

        reponse = navigateur.post("/laboutik/caisse/charger-plan-comptable/")

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        compte_du_bar.refresh_from_db()
        assert compte_du_bar.libelle_du_compte == "Ventes du bar (libellé du lieu)"
        categorie_du_bar.refresh_from_db()
        assert categorie_du_bar.compte_comptable_id == compte_du_bar.uuid
        numeros_presents = set(
            CompteComptable.objects.values_list("numero_de_compte", flat=True)
        )
        assert numeros_presents == NUMEROS_DU_PLAN_PAR_DEFAUT

    # ------------------------------------------------------------------ #
    #  Le filet / The safety net                                          #
    # ------------------------------------------------------------------ #

    def test_filet_charge_le_plan_si_aucun_compte(self):
        """Sans aucun compte, le filet charge tout le plan, une seule fois.
        / With no account, the safety net loads the whole plan, only once."""
        _vider_le_plan_du_lieu()

        s_assurer_que_le_plan_existe()
        s_assurer_que_le_plan_existe()

        numeros_presents = list(
            CompteComptable.objects.values_list("numero_de_compte", flat=True)
        )
        assert sorted(numeros_presents) == sorted(NUMEROS_DU_PLAN_PAR_DEFAUT)
        moyens_presents = list(
            MappingMoyenDePaiement.objects.values_list("moyen_de_paiement", flat=True)
        )
        assert sorted(moyens_presents) == sorted(COMPTE_ATTENDU_PAR_MOYEN.keys())

    def test_filet_ne_fait_rien_si_un_compte_existe(self):
        """Un seul compte suffit : le filet ne touche à rien.
        / A single account is enough: the safety net touches nothing."""
        _vider_le_plan_du_lieu()
        compte_unique_du_lieu = CompteComptable.objects.create(
            numero_de_compte="706100",
            libelle_du_compte="Billetterie du lieu",
            nature_du_compte=CompteComptable.VENTE,
        )

        s_assurer_que_le_plan_existe()

        assert list(CompteComptable.objects.all()) == [compte_unique_du_lieu]
        assert MappingMoyenDePaiement.objects.count() == 0

    # ------------------------------------------------------------------ #
    #  Unicité du numéro de compte / Account number uniqueness            #
    # ------------------------------------------------------------------ #

    def test_numero_de_compte_unique(self):
        """Deux comptes au même numéro dans un lieu : la base refuse.
        / Two accounts with the same number in a venue: the database refuses."""
        CompteComptable.objects.create(
            numero_de_compte="999990",
            libelle_du_compte="Compte de test",
            nature_du_compte=CompteComptable.SPECIAL,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CompteComptable.objects.create(
                    numero_de_compte="999990",
                    libelle_du_compte="Compte de test, en double",
                    nature_du_compte=CompteComptable.SPECIAL,
                )

    # ------------------------------------------------------------------ #
    #  La migration de chargement / The loading migration                 #
    # ------------------------------------------------------------------ #

    def test_migration_charge_le_plan_si_aucun_compte(self):
        """La fonction de la migration charge le plan dans un lieu sans compte.
        / The migration function loads the plan into a venue with no account."""
        _vider_le_plan_du_lieu()

        _lancer_la_fonction_de_migration(
            MIGRATION_DE_CHARGEMENT, FONCTION_DE_CHARGEMENT
        )

        numeros_presents = set(
            CompteComptable.objects.values_list("numero_de_compte", flat=True)
        )
        assert numeros_presents == NUMEROS_DU_PLAN_PAR_DEFAUT
        for moyen, numero_attendu in COMPTE_ATTENDU_PAR_MOYEN.items():
            correspondance = MappingMoyenDePaiement.objects.get(moyen_de_paiement=moyen)
            assert (
                correspondance.compte_de_tresorerie.numero_de_compte == numero_attendu
            ), moyen

    # ------------------------------------------------------------------ #
    #  Les catégories connues du chargeur / Categories known to the loader #
    # ------------------------------------------------------------------ #

    def test_categories_d_ecart_reliees_si_elles_existent(self):
        """Le chargement relie les catégories d'écart (758000 / 658000) quand elles
        existent ; il ne les crée pas.
        / Loading links the gap categories (758000 / 658000) when they exist; it does
        not create them."""
        noms_des_categories_d_ecart = [NOM_ECART_RECU_EN_PLUS, NOM_ECART_RECU_EN_MOINS]

        # 1. Les catégories n'existent pas : le chargement ne les crée pas.
        # / 1. The categories do not exist: loading does not create them.
        _vider_le_plan_du_lieu()
        CategorieProduct.objects.filter(name__in=noms_des_categories_d_ecart).delete()
        _charger_le_plan_par_la_commande(self.tenant.schema_name)
        assert not CategorieProduct.objects.filter(
            name__in=noms_des_categories_d_ecart
        ).exists()

        # 2. Les catégories existent, sans compte : le chargement les relie.
        # / 2. The categories exist, without account: loading links them.
        categorie_recu_en_plus = CategorieProduct.objects.create(
            name=NOM_ECART_RECU_EN_PLUS
        )
        categorie_recu_en_moins = CategorieProduct.objects.create(
            name=NOM_ECART_RECU_EN_MOINS
        )
        _charger_le_plan_par_la_commande(self.tenant.schema_name)

        categorie_recu_en_plus.refresh_from_db()
        categorie_recu_en_moins.refresh_from_db()
        assert categorie_recu_en_plus.compte_comptable.numero_de_compte == "758000"
        assert categorie_recu_en_moins.compte_comptable.numero_de_compte == "658000"

    def test_categorie_jetons_repris_reliee_au_623400(self):
        """Le chargement relie la catégorie « Jetons cadeau repris au vidage » au
        623400 (cadeaux à la clientèle) quand elle existe ; il ne la crée pas. Des
        jetons perdus au vidage annulent la dette (D8 bis).
        / Loading links the "gift tokens taken back" category to 623400 when it exists;
        it does not create it."""
        # Le nom vient du service de vente : le module du plan en garde une copie, ce
        # test échoue si les deux divergent.
        # / The name comes from the sale service: the plan module keeps a copy, this
        # test fails if both diverge.

        # 1. La catégorie n'existe pas : le chargement ne la crée pas.
        # / 1. The category does not exist: loading does not create it.
        _vider_le_plan_du_lieu()
        CategorieProduct.objects.filter(
            name=NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE
        ).delete()
        _charger_le_plan_par_la_commande(self.tenant.schema_name)
        assert not CategorieProduct.objects.filter(
            name=NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE
        ).exists()

        # 2. La catégorie existe, sans compte : le chargement la relie au 623400.
        # / 2. The category exists, without account: loading links it to 623400.
        categorie_des_jetons_repris = CategorieProduct.objects.create(
            name=NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE
        )
        _charger_le_plan_par_la_commande(self.tenant.schema_name)

        categorie_des_jetons_repris.refresh_from_db()
        assert (
            categorie_des_jetons_repris.compte_comptable.numero_de_compte == "623400"
        )

    def test_chargement_cree_la_categorie_des_crowds_et_y_range_leurs_produits(self):
        """Le chargement crée la catégorie « Financement participatif », la relie au
        754000 et y range les produits des contributions crowds qui n'ont pas de
        catégorie ; un produit crowds déjà rangé ailleurs ne bouge pas.
        / Loading creates the crowdfunding category, links it to 754000 and puts the
        crowds products without category in it; an already filed one does not move."""
        _vider_le_plan_du_lieu()
        CategorieProduct.objects.filter(
            name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
        ).delete()
        produit_crowds_sans_categorie = Product.objects.create(
            name="crowdfunding", categorie_article=Product.NONE, publish=False
        )
        categorie_choisie_par_le_lieu = CategorieProduct.objects.create(
            name="Catégorie choisie par le lieu"
        )
        produit_crowds_deja_range = Product.objects.create(
            name="Crowdfunding",
            categorie_article=Product.BILLET,
            categorie_pos=categorie_choisie_par_le_lieu,
            publish=False,
        )

        _charger_le_plan_par_la_commande(self.tenant.schema_name)

        categorie_financement_participatif = CategorieProduct.objects.get(
            name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
        )
        assert (
            categorie_financement_participatif.compte_comptable.numero_de_compte
            == "754000"
        )
        produit_crowds_sans_categorie.refresh_from_db()
        assert (
            produit_crowds_sans_categorie.categorie_pos_id
            == categorie_financement_participatif.uuid
        )
        produit_crowds_deja_range.refresh_from_db()
        assert (
            produit_crowds_deja_range.categorie_pos_id
            == categorie_choisie_par_le_lieu.uuid
        )

    def test_produit_crowds_cree_dans_la_categorie_du_financement_participatif(self):
        """Le produit des contributions crowds naît dans la catégorie « Financement
        participatif », reliée au 754000 : une contribution a donc un compte.
        / The crowds product is born in the crowdfunding category, linked to 754000."""
        Product.objects.filter(name__iexact="crowdfunding").delete()
        CategorieProduct.objects.filter(
            name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
        ).delete()

        tarif_des_contributions = _get_or_create_crowdfunding_price()

        produit_crowds = tarif_des_contributions.product
        assert produit_crowds.categorie_pos.name == NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
        assert produit_crowds.categorie_pos.compte_comptable.numero_de_compte == "754000"

    def test_produit_crowds_cree_avec_une_categorie_existante_sans_compte(self):
        """La catégorie « Financement participatif » existe déjà, sans compte : le
        produit crowds y est rangé et la catégorie est reliée au 754000.
        / The crowdfunding category already exists without account: the crowds
        product goes in it and the category is linked to 754000."""
        Product.objects.filter(name__iexact="crowdfunding").delete()
        CategorieProduct.objects.filter(
            name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
        ).delete()
        categorie_existante_sans_compte = CategorieProduct.objects.create(
            name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
        )

        tarif_des_contributions = _get_or_create_crowdfunding_price()

        produit_crowds = tarif_des_contributions.product
        assert produit_crowds.categorie_pos_id == categorie_existante_sans_compte.uuid
        categorie_existante_sans_compte.refresh_from_db()
        assert (
            categorie_existante_sans_compte.compte_comptable.numero_de_compte
            == "754000"
        )

    def test_migration_cree_la_categorie_des_crowds_si_elle_manque(self):
        """Sans catégorie « Financement participatif », la migration la crée, reliée
        au 754000, et y range le produit crowds sans catégorie.
        / Without the crowdfunding category, the migration creates it, linked to
        754000, and files the crowds product without category in it."""
        CategorieProduct.objects.filter(
            name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
        ).delete()
        produit_crowds_sans_categorie = Product.objects.create(
            name="crowdfunding", categorie_article=Product.NONE, publish=False
        )

        _lancer_la_fonction_de_migration(
            MIGRATION_DES_CROWDS, FONCTION_DE_LA_MIGRATION_DES_CROWDS
        )

        categories_creees = CategorieProduct.objects.filter(
            name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
        )
        assert categories_creees.count() == 1
        categorie_creee = categories_creees.get()
        assert categorie_creee.compte_comptable.numero_de_compte == "754000"
        produit_crowds_sans_categorie.refresh_from_db()
        assert produit_crowds_sans_categorie.categorie_pos_id == categorie_creee.uuid

    def test_migration_relie_la_categorie_des_crowds_et_range_leurs_produits(self):
        """La catégorie existe sans compte : la migration la relie au 754000 et y
        range les produits crowds sans catégorie ; un produit crowds déjà rangé
        ailleurs ne bouge pas ; la rejouer ne change rien.
        / The category exists without account: the migration links it to 754000 and
        files the crowds products without category; an already filed one does not
        move; replaying it changes nothing."""
        CategorieProduct.objects.filter(
            name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
        ).delete()
        categorie_existante_sans_compte = CategorieProduct.objects.create(
            name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
        )
        produit_crowds_sans_categorie = Product.objects.create(
            name="crowdfunding", categorie_article=Product.NONE, publish=False
        )
        categorie_choisie_par_le_lieu = CategorieProduct.objects.create(
            name="Catégorie choisie par le lieu (migration)"
        )
        produit_crowds_deja_range = Product.objects.create(
            name="Crowdfunding",
            categorie_article=Product.BILLET,
            categorie_pos=categorie_choisie_par_le_lieu,
            publish=False,
        )

        _lancer_la_fonction_de_migration(
            MIGRATION_DES_CROWDS, FONCTION_DE_LA_MIGRATION_DES_CROWDS
        )
        _lancer_la_fonction_de_migration(
            MIGRATION_DES_CROWDS, FONCTION_DE_LA_MIGRATION_DES_CROWDS
        )

        assert (
            CategorieProduct.objects.filter(
                name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
            ).count()
            == 1
        )
        categorie_existante_sans_compte.refresh_from_db()
        assert (
            categorie_existante_sans_compte.compte_comptable.numero_de_compte
            == "754000"
        )
        produit_crowds_sans_categorie.refresh_from_db()
        assert (
            produit_crowds_sans_categorie.categorie_pos_id
            == categorie_existante_sans_compte.uuid
        )
        produit_crowds_deja_range.refresh_from_db()
        assert (
            produit_crowds_deja_range.categorie_pos_id
            == categorie_choisie_par_le_lieu.uuid
        )

    # ------------------------------------------------------------------ #
    #  Le compte d'un règlement (§3.1) / A payment's account              #
    # ------------------------------------------------------------------ #

    def test_compte_de_la_monnaie_prioritaire_sur_le_moyen(self):
        """Une monnaie qui a son compte donne ce compte, même quand son moyen (`LE`)
        en a un autre. Vrai aussi pour la monnaie d'un autre lieu acceptée ici.
        / A currency with its own account gives that account, even when its payment
        method (LE) has another one. Also true for another venue's currency."""
        compte_de_la_peche = _creer_un_compte(
            "419200", "Monnaie locale « Pêche »", CompteComptable.TIERS
        )
        monnaie_du_lieu = _monnaie_fedow_core(self.tenant)
        MappingMonnaie.objects.create(
            asset_uuid=monnaie_du_lieu.uuid,
            compte_de_tresorerie=compte_de_la_peche,
        )

        compte_trouve = compte_pour_reglement("LE", monnaie_du_lieu.uuid)

        assert compte_trouve.numero_de_compte == "419200"

        # La monnaie d'un autre lieu, acceptée ici, avec son propre compte.
        # / Another venue's currency, accepted here, with its own account.
        compte_de_la_monnaie_federee = _creer_un_compte(
            "467100", "Monnaie fédérée d'un autre lieu", CompteComptable.TIERS
        )
        monnaie_d_un_autre_lieu = _monnaie_ancien_fedow(_un_autre_lieu())
        MappingMonnaie.objects.create(
            asset_uuid=monnaie_d_un_autre_lieu.uuid,
            compte_de_tresorerie=compte_de_la_monnaie_federee,
        )

        compte_trouve = compte_pour_reglement("LE", monnaie_d_un_autre_lieu.uuid)

        assert compte_trouve.numero_de_compte == "467100"

    def test_monnaie_du_lieu_sans_compte_repli_sur_le_moyen(self):
        """Sans monnaie, ou avec une monnaie du lieu sans compte (fedow_core ou ancien
        Fedow), le compte est celui du moyen de paiement.
        / Without currency, or with a venue currency without account (fedow_core or
        old Fedow), the account is the payment method's."""
        # Sans monnaie : espèces, carte bancaire.
        # / Without currency: cash, card.
        assert compte_pour_reglement("CA", None).numero_de_compte == "530000"
        assert compte_pour_reglement("CC", None).numero_de_compte == "512100"

        # La monnaie du lieu, moteur fedow_core (`tenant_origin` = le lieu).
        # / The venue's currency, fedow_core engine.
        monnaie_du_lieu_fedow_core = _monnaie_fedow_core(self.tenant)
        compte_trouve = compte_pour_reglement("LE", monnaie_du_lieu_fedow_core.uuid)
        assert compte_trouve.numero_de_compte == "419100"

        # La monnaie du lieu, ancien Fedow (`origin` = le lieu).
        # / The venue's currency, old Fedow.
        monnaie_du_lieu_ancien_fedow = _monnaie_ancien_fedow(self.tenant)
        compte_trouve = compte_pour_reglement("LE", monnaie_du_lieu_ancien_fedow.uuid)
        assert compte_trouve.numero_de_compte == "419100"

    def test_monnaie_d_un_autre_lieu_sans_compte_refus(self):
        """La monnaie d'un autre lieu sans compte : erreur, même si le moyen `LE` a
        un compte. Un compte par monnaie (mainteneur, 2026-10-02).
        / Another venue's currency without account: error, even if the LE method
        has an account. One account per currency."""
        monnaie_fedow_core_d_un_autre_lieu = _monnaie_fedow_core(_un_autre_lieu())
        with self.assertRaises(CompteComptableManquant) as erreur:
            compte_pour_reglement("LE", monnaie_fedow_core_d_un_autre_lieu.uuid)
        assert str(monnaie_fedow_core_d_un_autre_lieu.uuid) in str(erreur.exception)

        monnaie_ancien_fedow_d_un_autre_lieu = _monnaie_ancien_fedow(_un_autre_lieu())
        with self.assertRaises(CompteComptableManquant) as erreur:
            compte_pour_reglement("LE", monnaie_ancien_fedow_d_un_autre_lieu.uuid)
        assert str(monnaie_ancien_fedow_d_un_autre_lieu.uuid) in str(erreur.exception)

    def test_fed_ses_deux_uuid_vont_au_467(self):
        """Le chargeur relie les deux uuid du FED (fedow_core et ancien Fedow) au
        467000 ; un règlement `SF` passe toujours par sa monnaie, jamais par le
        moyen `SF`, même si le lieu lui a donné un compte.
        / The loader links both FED uuids to 467000; an SF payment always goes
        through its currency, never through the SF method."""
        # Le FED de fedow_core : la garde de `Asset.save()` refuse un FED local
        # hors des tests qui la lèvent.
        # / The fedow_core FED: Asset.save() refuses a local FED unless lifted.
        fed_de_fedow_core = Asset.objects.filter(category=Asset.FED).first()
        if fed_de_fedow_core is None:
            with self.settings(FEDOW_AUTORISER_ASSET_FED_LOCAL=True):
                fed_de_fedow_core = _monnaie_fedow_core(
                    _un_autre_lieu(), categorie=Asset.FED
                )
        fed_de_l_ancien_fedow = AssetFedowPublic.objects.filter(
            category=AssetFedowPublic.STRIPE_FED_FIAT
        ).first()
        if fed_de_l_ancien_fedow is None:
            fed_de_l_ancien_fedow = _monnaie_ancien_fedow(
                _un_autre_lieu(), categorie=AssetFedowPublic.STRIPE_FED_FIAT
            )

        # Une correspondance pour le moyen SF, posée exprès : elle ne doit jamais
        # servir.
        # / A mapping for the SF method, set on purpose: it must never be used.
        MappingMoyenDePaiement.objects.create(
            moyen_de_paiement="SF",
            libelle_moyen="Stripe fédéré (ne doit pas servir)",
            compte_de_tresorerie=_compte("517100"),
        )

        # Deux chargements : le second n'ajoute rien.
        # / Two loads: the second adds nothing.
        charger_le_plan_comptable_par_defaut()
        charger_le_plan_comptable_par_defaut()

        for uuid_du_fed in [fed_de_fedow_core.uuid, fed_de_l_ancien_fedow.uuid]:
            correspondances_du_fed = MappingMonnaie.objects.filter(
                asset_uuid=uuid_du_fed
            )
            assert correspondances_du_fed.count() == 1, uuid_du_fed
            compte_du_fed = correspondances_du_fed.get().compte_de_tresorerie
            assert compte_du_fed.numero_de_compte == "467000", uuid_du_fed

            compte_trouve = compte_pour_reglement("SF", uuid_du_fed)
            assert compte_trouve.numero_de_compte == "467000", uuid_du_fed

        # SF sans monnaie : aucun compte, même si le moyen SF en a un.
        # / SF without currency: no account, even if the SF method has one.
        with self.assertRaises(CompteComptableManquant):
            compte_pour_reglement("SF", None)

    def test_ni_monnaie_ni_moyen_erreur_explicite(self):
        """Un moyen sans correspondance et sans monnaie : erreur qui nomme le moyen.
        / A method without mapping and without currency: error naming the method."""
        MappingMoyenDePaiement.objects.filter(moyen_de_paiement="CH").delete()

        with self.assertRaises(CompteComptableManquant) as erreur:
            compte_pour_reglement("CH", None)

        assert "CH" in str(erreur.exception)

    def test_correspondance_de_moyen_au_compte_vide_erreur(self):
        """Une correspondance de moyen au compte vide : erreur, jamais une ligne
        sautée en silence (D23).
        / A method mapping with an empty account: error, never a silently skipped
        line."""
        correspondance_cheque = MappingMoyenDePaiement.objects.get(
            moyen_de_paiement="CH"
        )
        correspondance_cheque.compte_de_tresorerie = None
        correspondance_cheque.save()

        with self.assertRaises(CompteComptableManquant) as erreur:
            compte_pour_reglement("CH", None)

        assert "CH" in str(erreur.exception)

    def test_migration_relie_le_fed_au_467(self):
        """La migration de données relie les deux uuid du FED au 467000 dans un lieu
        déjà chargé ; une correspondance existante n'est pas touchée ; la rejouer ne
        change rien.
        / The data migration links both FED uuids to 467000 in an already loaded
        venue; an existing mapping is kept; replaying it changes nothing."""
        fed_de_fedow_core = Asset.objects.filter(category=Asset.FED).first()
        if fed_de_fedow_core is None:
            with self.settings(FEDOW_AUTORISER_ASSET_FED_LOCAL=True):
                fed_de_fedow_core = _monnaie_fedow_core(
                    _un_autre_lieu(), categorie=Asset.FED
                )
        fed_de_l_ancien_fedow = AssetFedowPublic.objects.filter(
            category=AssetFedowPublic.STRIPE_FED_FIAT
        ).first()
        if fed_de_l_ancien_fedow is None:
            fed_de_l_ancien_fedow = _monnaie_ancien_fedow(
                _un_autre_lieu(), categorie=AssetFedowPublic.STRIPE_FED_FIAT
            )

        # Le FED de l'ancien Fedow a déjà un compte choisi par le lieu.
        # / The old-Fedow FED already has an account chosen by the venue.
        MappingMonnaie.objects.filter(
            asset_uuid__in=[fed_de_fedow_core.uuid, fed_de_l_ancien_fedow.uuid]
        ).delete()
        compte_choisi_par_le_lieu = _creer_un_compte(
            "467500", "Réseau fédéré (compte du lieu)", CompteComptable.TIERS
        )
        MappingMonnaie.objects.create(
            asset_uuid=fed_de_l_ancien_fedow.uuid,
            compte_de_tresorerie=compte_choisi_par_le_lieu,
        )

        _lancer_la_fonction_de_migration(
            MIGRATION_DU_FED, FONCTION_DE_LA_MIGRATION_DU_FED
        )
        _lancer_la_fonction_de_migration(
            MIGRATION_DU_FED, FONCTION_DE_LA_MIGRATION_DU_FED
        )

        correspondances_du_fed_de_fedow_core = MappingMonnaie.objects.filter(
            asset_uuid=fed_de_fedow_core.uuid
        )
        assert correspondances_du_fed_de_fedow_core.count() == 1
        assert (
            correspondances_du_fed_de_fedow_core.get().compte_de_tresorerie.numero_de_compte
            == "467000"
        )
        correspondance_du_fed_de_l_ancien_fedow = MappingMonnaie.objects.get(
            asset_uuid=fed_de_l_ancien_fedow.uuid
        )
        assert (
            correspondance_du_fed_de_l_ancien_fedow.compte_de_tresorerie_id
            == compte_choisi_par_le_lieu.uuid
        )

    def test_moyens_hors_argent_sans_ecriture(self):
        """`NA` (offert) et `NM` (points, temps) n'écrivent pas d'argent : la
        fonction rend None, sans erreur, même avec une monnaie.
        / NA (offered) and NM (points, time) write no money: the function returns
        None, without error, even with a currency."""
        assert compte_pour_reglement("NA", None) is None
        assert compte_pour_reglement("NM", None) is None

        monnaie_de_points = _monnaie_ancien_fedow(
            self.tenant, categorie=AssetFedowPublic.FIDELITY
        )
        assert compte_pour_reglement("NM", monnaie_de_points.uuid) is None

    # ------------------------------------------------------------------ #
    #  Le journal (§3.2) / The journal                                    #
    # ------------------------------------------------------------------ #

    def test_journal_du_point_de_vente_lettres_seules(self):
        """Le point de vente gagne sur l'origine. Son code renseigné sert tel quel ;
        sans code, il est dérivé du nom : majuscules, sans accent, lettres seules,
        10 caractères au plus.
        / The point of sale wins over the origin. Its code is used as is; without
        code, it is derived from the name (uppercase, no accent, letters, 10 max)."""
        bar_avec_code = _point_de_vente("Bar du haut", code_journal="BAR")
        for origine in ["LB", "TI", "LP", "AD"]:
            assert journal_pour(bar_avec_code, origine) == "BAR", origine

        # « Buvette d'Été 2 » → BUVETTEDETE → 10 lettres : BUVETTEDET.
        # / "Buvette d'Été 2" → BUVETTEDETE → 10 letters: BUVETTEDET.
        buvette_sans_code = _point_de_vente("Buvette d'Été 2")
        for origine in ["LB", "TI", "LP", "AD"]:
            assert journal_pour(buvette_sans_code, origine) == "BUVETTEDET", origine

    def test_journal_d_un_point_de_vente_au_nom_sans_lettre_erreur(self):
        """Un point de vente sans code, au nom sans aucune lettre : pas de code à
        dériver, erreur qui nomme le point de vente.
        / A point of sale without code, named without any letter: error naming it."""
        point_de_vente_sans_lettre = _point_de_vente("123")

        with self.assertRaises(CompteComptableManquant) as erreur:
            journal_pour(point_de_vente_sans_lettre, "LB")

        assert "123" in str(erreur.exception)

    def test_code_journal_refuse_autre_chose_que_des_lettres(self):
        """Le code journal n'accepte que des lettres majuscules (profil PennyLane),
        10 au plus ; vide est permis.
        / The journal code only accepts uppercase letters, 10 max; empty is allowed."""
        codes_refuses = ["BAR1", "bar", "BAR-2", "BAR ", "ÉTÉ", "ABCDEFGHIJK"]
        for code_refuse in codes_refuses:
            point_de_vente = PointDeVente(
                name=f"Point de vente {identifiant_unique()}", code_journal=code_refuse
            )
            with self.assertRaises(ValidationError) as erreur:
                point_de_vente.full_clean()
            assert "code_journal" in erreur.exception.message_dict, code_refuse

        codes_acceptes = ["BAR", "TIREUSE", ""]
        for code_accepte in codes_acceptes:
            point_de_vente = PointDeVente(
                name=f"Point de vente {identifiant_unique()}", code_journal=code_accepte
            )
            point_de_vente.full_clean()

    def test_journal_par_defaut_selon_origine(self):
        """Sans point de vente, le journal suit la table des neuf origines ; une
        origine inconnue lève une erreur qui la nomme.
        / Without point of sale, the journal follows the nine-origin table; an
        unknown origin raises an error naming it."""
        # La table couvre toutes les origines du code : une origine ajoutée plus
        # tard fait échouer ce test, il faut alors lui donner un journal.
        # / The table covers every origin: a new origin makes this test fail.
        assert set(SaleOrigin.values) == set(JOURNAL_ATTENDU_PAR_ORIGINE.keys())

        for origine, journal_attendu in JOURNAL_ATTENDU_PAR_ORIGINE.items():
            assert journal_pour(None, origine) == journal_attendu, origine

        with self.assertRaises(CompteComptableManquant) as erreur:
            journal_pour(None, "ZZ")
        assert "ZZ" in str(erreur.exception)

    def test_code_journal_collision_signalee(self):
        """Deux points de vente qui donnent le même code (l'un renseigné, l'autre
        dérivé du nom) sont signalés ; un code unique ne l'est pas.
        / Two points of sale giving the same code (one set, one derived from the
        name) are reported; a unique code is not."""
        buvette_avec_code = _point_de_vente("Buvette du haut", code_journal="BUVETTE")
        buvette_sans_code = _point_de_vente("Buvette")
        _point_de_vente("Cuisine", code_journal="CUISINE")

        collisions = collisions_de_codes_journal()

        assert "BUVETTE" in collisions
        uuids_en_collision = set()
        for point_de_vente in collisions["BUVETTE"]:
            uuids_en_collision.add(point_de_vente.uuid)
        assert uuids_en_collision == {buvette_avec_code.uuid, buvette_sans_code.uuid}
        assert "CUISINE" not in collisions

    # ------------------------------------------------------------------ #
    #  Le compte d'un article (§3.3) / An item's account                  #
    # ------------------------------------------------------------------ #

    def test_compte_article_ordre_des_regles(self):
        """Les règles du compte d'un article, dans l'ordre de la fiche §3.3.
        / The item account rules, in the order of sheet §3.3."""
        compte_du_bar = _compte("707000")

        # Règle 0 : une recharge rangée dans une catégorie 7xx va au 419100 (la
        # catégorie est ignorée pour un article hors chiffre d'affaires).
        # / Rule 0: a top-up in a 7xx category goes to 419100 (category ignored).
        recharge_euros = creer_tarif_vendu(
            nom="Recharge euros", methode_caisse=Product.RECHARGE_EUROS
        )
        _ranger_dans_une_categorie(recharge_euros, compte_du_bar)
        ligne = _ligne_d_article(recharge_euros, hors_chiffre_affaires=True)
        assert compte_pour_article(ligne).numero_de_compte == "419100"

        recharge_cadeau = creer_tarif_vendu(
            nom="Recharge cadeau", methode_caisse=Product.RECHARGE_CADEAU
        )
        ligne = _ligne_d_article(recharge_cadeau, hors_chiffre_affaires=True)
        assert compte_pour_article(ligne).numero_de_compte == "419100"

        # Règle 0 : la recharge de l'API v2 (type `R`, sans mode de caisse).
        # / Rule 0: the API v2 top-up (type R, no POS method).
        recharge_api_v2 = creer_tarif_vendu(
            nom="Recharge API v2", categorie_article=Product.RECHARGE_CASHLESS
        )
        ligne = _ligne_d_article(recharge_api_v2, hors_chiffre_affaires=True)
        assert compte_pour_article(ligne).numero_de_compte == "419100"

        # Règle 0 : la recharge FED en ligne (type `E`). Le service de vente la marque
        # hors chiffre d'affaires, mais la règle ne lit pas ce marqueur : elle lit le
        # type du produit (ligne posée ici sans le marqueur, exprès).
        # / Rule 0: the online FED top-up (type E). The rule reads the product type,
        # not the off-revenue flag (line built here without the flag, on purpose).
        recharge_fed = creer_tarif_vendu(
            nom="Recharge FED", categorie_article=Product.RECHARGE_CASHLESS_FED
        )
        ligne = _ligne_d_article(recharge_fed)
        assert compte_pour_article(ligne).numero_de_compte == "419100"

        # Règle 0 : le virement du pot central va au compte de SA monnaie, même rangé
        # dans une catégorie 7xx.
        # / Rule 0: the central pot transfer goes to ITS currency's account.
        monnaie_du_virement = _monnaie_ancien_fedow(_un_autre_lieu())
        MappingMonnaie.objects.create(
            asset_uuid=monnaie_du_virement.uuid,
            compte_de_tresorerie=_compte("467000"),
        )
        virement_recu = creer_tarif_vendu(
            nom="Virement du pot central", methode_caisse=Product.VIREMENT_RECU
        )
        _ranger_dans_une_categorie(virement_recu, compte_du_bar)
        ligne = _ligne_d_article(
            virement_recu,
            hors_chiffre_affaires=True,
            asset=monnaie_du_virement.uuid,
        )
        assert compte_pour_article(ligne).numero_de_compte == "467000"

        # Règle 1 : le retour de consigne prend le compte de la vente de la consigne
        # (le gobelet), pas celui de sa propre catégorie.
        # / Rule 1: the deposit return takes the deposit sale's account (the cup).
        compte_des_consignes = _creer_un_compte(
            "419600", "Consignes des gobelets", CompteComptable.TIERS
        )
        gobelet = creer_tarif_vendu(nom="Gobelet", methode_caisse=Product.VENTE)
        _ranger_dans_une_categorie(gobelet, compte_des_consignes)
        retour_de_gobelet = creer_tarif_vendu(
            nom="Retour gobelet", methode_caisse=Product.RETOUR_CONSIGNE
        )
        _ranger_dans_une_categorie(retour_de_gobelet, compte_du_bar)
        produit_du_retour = retour_de_gobelet.productsold.product
        produit_du_retour.consigne_remboursee = gobelet.productsold.product
        produit_du_retour.save()
        ligne = _ligne_d_article(retour_de_gobelet)
        assert compte_pour_article(ligne).numero_de_compte == "419600"

        # Règle 2 : le bar, par la catégorie de caisse.
        # / Rule 2: the bar, through the POS category.
        biere = creer_tarif_vendu(nom="Bière", methode_caisse=Product.VENTE)
        _ranger_dans_une_categorie(biere, compte_du_bar)
        ligne = _ligne_d_article(biere)
        assert compte_pour_article(ligne).numero_de_compte == "707000"

        # Règle 2 : les crowds, par la catégorie « Financement participatif » que le
        # chargeur relie au 754000.
        # / Rule 2: crowds, through the category the loader links to 754000.
        categorie_financement_participatif = CategorieProduct.objects.create(
            name=NOM_CATEGORIE_FINANCEMENT_PARTICIPATIF
        )
        charger_le_plan_comptable_par_defaut()
        categorie_financement_participatif.refresh_from_db()
        contribution_crowds = creer_tarif_vendu(
            nom="crowdfunding", categorie_article=Product.NONE
        )
        produit_crowds = contribution_crowds.productsold.product
        produit_crowds.categorie_pos = categorie_financement_participatif
        produit_crowds.save()
        ligne = _ligne_d_article(contribution_crowds)
        assert compte_pour_article(ligne).numero_de_compte == "754000"

        # Règle 3 : par le mode de caisse, sans catégorie (type de produit N : seul
        # le mode de caisse donne le compte).
        # / Rule 3: by POS method, without category (type N: only the method).
        adhesion_a_la_caisse = creer_tarif_vendu(
            nom="Adhésion caisse", methode_caisse=Product.ADHESION_POS
        )
        ligne = _ligne_d_article(adhesion_a_la_caisse)
        assert compte_pour_article(ligne).numero_de_compte == "756000"

        billet_a_la_caisse = creer_tarif_vendu(
            nom="Billet caisse", methode_caisse=Product.BILLET_POS
        )
        ligne = _ligne_d_article(billet_a_la_caisse)
        assert compte_pour_article(ligne).numero_de_compte == "706000"

        # Règle 4 : par le type de produit, sans catégorie ni mode de caisse (vente
        # en ligne).
        # / Rule 4: by product type, without category or POS method (online).
        for type_de_produit, numero_attendu in COMPTE_ATTENDU_PAR_TYPE_DE_PRODUIT.items():
            produit_en_ligne = creer_tarif_vendu(
                nom=f"En ligne {type_de_produit}", categorie_article=type_de_produit
            )
            ligne = _ligne_d_article(produit_en_ligne)
            compte_trouve = compte_pour_article(ligne)
            assert compte_trouve.numero_de_compte == numero_attendu, type_de_produit

    def test_compte_article_sans_regle_refus(self):
        """Un article qu'aucune règle ne couvre lève une erreur qui nomme le produit :
        type `N` / `U` ou mode `VT` / `FR` sans catégorie, modes `TM` et `FD` avec ou
        sans catégorie.
        / An item no rule covers raises an error naming the product."""
        # TM et FD rangés dans une catégorie reliée à un compte : erreur quand même.
        # / TM and FD in a category linked to an account: error anyway.
        temps_dans_une_categorie = creer_tarif_vendu(
            nom="Temps rangé", methode_caisse=Product.RECHARGE_TEMPS
        )
        _ranger_dans_une_categorie(temps_dans_une_categorie, _compte("707000"))
        fidelite_dans_une_categorie = creer_tarif_vendu(
            nom="Fidélité rangée", methode_caisse=Product.FIDELITE
        )
        _ranger_dans_une_categorie(fidelite_dans_une_categorie, _compte("707000"))

        articles_sans_regle = [
            (creer_tarif_vendu(nom="Sans type"), False),
            (creer_tarif_vendu(nom="Fût", categorie_article=Product.FUT), False),
            (creer_tarif_vendu(nom="Vente", methode_caisse=Product.VENTE), False),
            (
                creer_tarif_vendu(
                    nom="Fractionné", methode_caisse=Product.FRACTIONNE_POS
                ),
                False,
            ),
            # TM et FD sont hors chiffre d'affaires pour le service de vente.
            # / TM and FD are off revenue for the sale service.
            (
                creer_tarif_vendu(nom="Temps", methode_caisse=Product.RECHARGE_TEMPS),
                True,
            ),
            (creer_tarif_vendu(nom="Fidélité", methode_caisse=Product.FIDELITE), True),
            (temps_dans_une_categorie, True),
            (fidelite_dans_une_categorie, True),
        ]
        for tarif_vendu, hors_chiffre_affaires in articles_sans_regle:
            nom_du_produit = tarif_vendu.productsold.product.name
            ligne = _ligne_d_article(
                tarif_vendu, hors_chiffre_affaires=hors_chiffre_affaires
            )
            with self.assertRaises(CompteComptableManquant) as erreur:
                compte_pour_article(ligne)
            assert nom_du_produit in str(erreur.exception), nom_du_produit

    def test_retour_de_consigne_sans_compte_de_consigne_erreur(self):
        """Un retour de consigne prend le compte de la catégorie de sa consigne : si
        la consigne n'a pas de catégorie, ou s'il n'y a pas de consigne, erreur —
        même quand le retour a sa propre catégorie reliée à un compte.
        / A deposit return takes its deposit's category account: no category on the
        deposit, or no deposit at all, raises — even if the return has a category."""
        gobelet_sans_categorie = creer_tarif_vendu(
            nom="Gobelet sans catégorie", methode_caisse=Product.VENTE
        )
        retour_d_un_gobelet_sans_categorie = creer_tarif_vendu(
            nom="Retour gobelet sans catégorie", methode_caisse=Product.RETOUR_CONSIGNE
        )
        _ranger_dans_une_categorie(retour_d_un_gobelet_sans_categorie, _compte("707000"))
        produit_du_retour = retour_d_un_gobelet_sans_categorie.productsold.product
        produit_du_retour.consigne_remboursee = gobelet_sans_categorie.productsold.product
        produit_du_retour.save()

        retour_sans_consigne = creer_tarif_vendu(
            nom="Retour sans consigne", methode_caisse=Product.RETOUR_CONSIGNE
        )
        _ranger_dans_une_categorie(retour_sans_consigne, _compte("707000"))

        for tarif_du_retour in [retour_d_un_gobelet_sans_categorie, retour_sans_consigne]:
            nom_du_retour = tarif_du_retour.productsold.product.name
            ligne = _ligne_d_article(tarif_du_retour)
            with self.assertRaises(CompteComptableManquant) as erreur:
                compte_pour_article(ligne)
            assert nom_du_retour in str(erreur.exception), nom_du_retour

    def test_ecarts_758_et_658(self):
        """Les deux écarts d'encaissement vont à deux comptes distincts, par leur
        nom : 758000 (reçu en plus), 658000 (reçu en moins). Leur catégorie de caisse
        est ignorée, même reliée à un compte de ventes.
        / Both collection gaps go to two distinct accounts, by their name. Their POS
        category is ignored, even linked to a sales account."""
        tarif_recu_en_plus = tarif_vendu_d_ecart_d_encaissement(NOM_ECART_RECU_EN_PLUS)
        tarif_recu_en_moins = tarif_vendu_d_ecart_d_encaissement(
            NOM_ECART_RECU_EN_MOINS
        )
        CategorieProduct.objects.filter(
            name__in=[NOM_ECART_RECU_EN_PLUS, NOM_ECART_RECU_EN_MOINS]
        ).update(compte_comptable=_compte("707000"))

        ligne_recu_en_plus = _ligne_d_article(
            tarif_recu_en_plus, hors_chiffre_affaires=True
        )
        ligne_recu_en_moins = _ligne_d_article(
            tarif_recu_en_moins, hors_chiffre_affaires=True
        )

        assert compte_pour_article(ligne_recu_en_plus).numero_de_compte == "758000"
        assert compte_pour_article(ligne_recu_en_moins).numero_de_compte == "658000"

    def test_compte_pour_article_jetons_repris_623400(self):
        """L'article « Jetons cadeau repris au vidage » va au 623400 (cadeaux à la
        clientèle), par le nom de son produit système : la dette des jetons perdus est
        annulée (D8 bis). Sa catégorie de caisse est ignorée, même reliée à un compte
        de ventes.
        / The "gift tokens taken back" item goes to 623400, by its system product's
        name. Its POS category is ignored, even linked to a sales account."""
        # Le produit système, fabriqué ici avec son nom constant (le test ne dépend
        # pas de la fonction du service qui le crée), rangé dans une catégorie reliée
        # au 707000.
        # / The system product, built here with its constant name, filed in a
        # category linked to 707000.
        produit_des_jetons_repris = Product.objects.create(
            name=NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE,
            categorie_article=Product.NONE,
            publish=False,
        )
        tarif_des_jetons_repris = Price.objects.create(
            product=produit_des_jetons_repris,
            name=NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE,
            prix=Decimal("0"),
            publish=False,
        )
        produit_vendu = ProductSold.objects.create(product=produit_des_jetons_repris)
        tarif_vendu_des_jetons_repris = PriceSold.objects.create(
            productsold=produit_vendu,
            price=tarif_des_jetons_repris,
            prix=tarif_des_jetons_repris.prix,
        )
        _ranger_dans_une_categorie(tarif_vendu_des_jetons_repris, _compte("707000"))

        ligne_des_jetons_repris = _ligne_d_article(
            tarif_vendu_des_jetons_repris, hors_chiffre_affaires=True
        )
        # Le vidage écrit cet article au moyen historique LG : la règle par le nom
        # donne 623400, le moyen de la ligne n'est jamais lu.
        # / The emptying writes this item with the LG method: the name rule gives
        # 623400; the line's method is never read.
        ligne_des_jetons_repris.payment_method = PaymentMethod.LOCAL_GIFT

        assert (
            compte_pour_article(ligne_des_jetons_repris).numero_de_compte == "623400"
        )

    def test_jetons_au_707900_et_compte_pour_article_rend_le_compte_du_reste(self):
        """Un jeton dépensé solde la dette du lieu (D8 bis) : la part payée en jetons
        d'un article va au 707900 « ventes réglées en jetons offerts »
        (`compte_des_ventes_reglees_en_jetons`). `compte_pour_article` rend le compte
        du RESTE de l'article (sa catégorie, 707000), sans lire le moyen de la ligne :
        la même bière, au moyen LG ou LE, a le même compte de reste.
        / The token part goes to 707900; compte_pour_article gives the remainder's
        account (its category), never reading the line's method."""
        biere = creer_tarif_vendu(nom="Bière", methode_caisse=Product.VENTE)
        _ranger_dans_une_categorie(biere, _compte("707000"))

        part_payee_en_jetons = _ligne_d_article(biere)
        part_payee_en_jetons.payment_method = PaymentMethod.LOCAL_GIFT
        part_payee_en_monnaie_locale = _ligne_d_article(biere)
        part_payee_en_monnaie_locale.payment_method = PaymentMethod.LOCAL_EURO

        assert compte_des_ventes_reglees_en_jetons().numero_de_compte == "707900"
        assert compte_pour_article(part_payee_en_jetons).numero_de_compte == "707000"
        assert (
            compte_pour_article(part_payee_en_monnaie_locale).numero_de_compte
            == "707000"
        )

    # ------------------------------------------------------------------ #
    #  Le FEC lit le plan du lieu / The FEC reads the venue's plan         #
    # ------------------------------------------------------------------ #

    def test_tva_cherchee_par_taux(self):
        """Le FEC prend le compte de TVA du lieu à ce taux, quel que soit son
        numéro : 20 % au numéro du lieu, 2,1 % et 5,5 % aux numéros du plan. Trois
        articles vendus en espèces, un par taux.
        / The FEC takes the venue's VAT account at that rate, whatever its number."""
        _preparer_la_caisse()
        _compte("445711").delete()
        CompteComptable.objects.create(
            numero_de_compte="445700",
            libelle_du_compte="TVA collectée 20 % (numéro du lieu)",
            nature_du_compte=CompteComptable.TVA,
            taux_de_tva=Decimal("20.00"),
        )
        for taux_tva in ["20", "5.5", "2.1"]:
            tarif_vendu = creer_tarif_vendu(nom=f"Article à {taux_tva} %")
            _ranger_dans_une_categorie(tarif_vendu, _compte("706000"))
            _vendre(tarif_vendu, moyen="CA", taux_tva=taux_tva)
        cloture = _cloture_j_des_ventes_du_test()

        lignes_du_fec = _lignes_du_fec(cloture)

        # Les comptes de TVA écrits, reconnus par leur nature dans le plan du lieu.
        # / The written VAT accounts, recognised by their nature in the venue's plan.
        numeros_des_comptes_de_tva = set(
            CompteComptable.objects.filter(
                nature_du_compte=CompteComptable.TVA
            ).values_list("numero_de_compte", flat=True)
        )
        comptes_de_tva_ecrits = []
        for ligne in lignes_du_fec:
            if ligne["CompteNum"] in numeros_des_comptes_de_tva:
                comptes_de_tva_ecrits.append(ligne["CompteNum"])
        assert sorted(comptes_de_tva_ecrits) == ["445700", "445713", "445714"]

    def test_fec_lit_le_plan_de_la_caisse(self):
        """Le FEC lit le plan de la caisse : les correspondances des moyens
        (`laboutik.MappingMoyenDePaiement`) et les comptes (`laboutik.CompteComptable`,
        numéro et libellé du lieu), pour les moyens, les billets et les adhésions. Un
        billet (TVA 20 %) payé en espèces, une adhésion (TVA 0) payée par Stripe.
        / The FEC reads the register's plan: method mappings and accounts
        (number and venue label), for methods, tickets and memberships."""
        _preparer_la_caisse()
        # Le lieu envoie ses espèces vers son propre compte, et renomme deux comptes.
        # / The venue sends its cash to its own account and renames two accounts.
        compte_de_la_caisse_du_bar = _creer_un_compte(
            "530100", "Caisse du bar", CompteComptable.TRESORERIE
        )
        correspondance_especes = MappingMoyenDePaiement.objects.get(
            moyen_de_paiement="CA"
        )
        correspondance_especes.compte_de_tresorerie = compte_de_la_caisse_du_bar
        correspondance_especes.save()
        compte_des_billets = _compte("706000")
        compte_des_billets.libelle_du_compte = "Billetterie (libellé du lieu)"
        compte_des_billets.save()
        compte_des_cotisations = _compte("756000")
        compte_des_cotisations.libelle_du_compte = "Cotisations (libellé du lieu)"
        compte_des_cotisations.save()

        tarif_du_billet = creer_tarif_vendu(
            nom="Billet", categorie_article=Product.BILLET
        )
        tarif_de_l_adhesion = creer_tarif_vendu(
            nom="Adhésion", taux_tva="0.00", categorie_article=Product.ADHESION
        )
        _vendre(tarif_du_billet, moyen="CA", taux_tva="20")
        _vendre(tarif_de_l_adhesion, moyen="SN", taux_tva="0")
        cloture = _cloture_j_des_ventes_du_test()

        lignes_du_fec = _lignes_du_fec(cloture)

        comptes_ecrits = set()
        for ligne in lignes_du_fec:
            comptes_ecrits.add((ligne["CompteNum"], ligne["CompteLib"]))
        assert comptes_ecrits == {
            ("530100", "Caisse du bar"),
            ("517100", "Stripe (fonds en attente de virement)"),
            ("706000", "Billetterie (libellé du lieu)"),
            ("756000", "Cotisations (libellé du lieu)"),
            ("445711", "TVA collectée 20 %"),
        }

    # ------------------------------------------------------------------ #
    #  Les écrans pour un bénévole (fiche §4) / Volunteer screens         #
    # ------------------------------------------------------------------ #

    def test_menu_ventes_et_comptabilite_a_les_trois_ecrans(self):
        """La section « Ventes & comptabilité » montre, sous « Ventes », le plan
        comptable, les comptes des moyens de paiement et les comptes des monnaies,
        dans cet ordre, que le module caisse soit actif ou non (le plan sert aussi
        aux ventes en ligne).
        / The "Sales & accounting" section shows, under "Sales", the chart of
        accounts, the payment method accounts and the currency accounts, in that
        order, whether the POS module is on or off."""
        lien_des_ventes = reverse("staff_admin:BaseBillet_vente_changelist")
        titre_attendu_par_lien = {
            reverse("staff_admin:laboutik_comptecomptable_changelist"): gettext(
                "Plan comptable"
            ),
            reverse("staff_admin:laboutik_mappingmoyendepaiement_changelist"): gettext(
                "Comptes des moyens de paiement"
            ),
            reverse("staff_admin:laboutik_mappingmonnaie_changelist"): gettext(
                "Comptes des monnaies"
            ),
        }
        liens_dans_l_ordre_attendu = list(titre_attendu_par_lien.keys())
        titre_de_la_section = gettext("Sales & accounting")

        for module_caisse_actif in [True, False]:
            # La configuration est forcée EN MÉMOIRE, jamais sauvée (PIEGES 13.5).
            # / The configuration is forced IN MEMORY, never saved.
            configuration = Configuration.get_solo()
            configuration.module_caisse = module_caisse_actif
            with patch.object(
                dashboard.Configuration, "get_solo", return_value=configuration
            ):
                sections = dashboard._construire_sections_modules(
                    RequestFactory().get("/admin/")
                )

            sections_ventes = []
            for section in sections:
                if str(section.get("title", "")) == titre_de_la_section:
                    sections_ventes.append(section)
            assert len(sections_ventes) == 1, module_caisse_actif

            liens_de_la_section = []
            titre_par_lien = {}
            for item in sections_ventes[0]["items"]:
                lien = str(item.get("link"))
                liens_de_la_section.append(lien)
                titre_par_lien[lien] = str(item.get("title"))

            for lien, titre_attendu in titre_attendu_par_lien.items():
                assert lien in liens_de_la_section, (
                    f"Module caisse {module_caisse_actif} : « {titre_attendu} » "
                    f"({lien}) absent. Liens trouvés : {liens_de_la_section}"
                )
                assert titre_par_lien[lien] == titre_attendu, lien

            # Sous « Ventes », dans l'ordre : plan, moyens, monnaies.
            # / Under "Sales", in order: plan, methods, currencies.
            positions = [liens_de_la_section.index(lien_des_ventes)]
            for lien in liens_dans_l_ordre_attendu:
                positions.append(liens_de_la_section.index(lien))
            assert positions == sorted(positions), liens_de_la_section

    def test_plan_comptable_regroupe_par_nature_avec_une_aide_par_nature(self):
        """La liste des comptes est regroupée par nature (les comptes d'une même
        nature se suivent), et chaque nature présente a sa phrase d'aide. L'aide des
        ventes dit que 754 et 756 sont des comptes d'association (un bar en société
        utilise 706 / 707).
        / The account list is grouped by nature, each present nature has its help
        sentence; the sales help says 754 / 756 are association accounts."""
        navigateur, _administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)

        # La page est demandée en français : l'aide est comparée à un mot français
        # (« association »). Une traduction anglaise ne casse pas le test.
        # / The page is asked in French: the help is compared to a French word.
        reponse = navigateur.get(
            reverse("staff_admin:laboutik_comptecomptable_changelist"),
            HTTP_ACCEPT_LANGUAGE="fr",
        )

        assert reponse.status_code == 200
        contenu = reponse.content.decode()

        # Regroupée : une nature ne réapparaît pas après une autre.
        # / Grouped: a nature does not show up again after another one.
        natures_dans_l_ordre_de_la_liste = []
        for compte in reponse.context["cl"].result_list:
            natures_dans_l_ordre_de_la_liste.append(compte.nature_du_compte)
        natures_deja_vues = []
        for nature in natures_dans_l_ordre_de_la_liste:
            if natures_deja_vues and natures_deja_vues[-1] == nature:
                continue
            assert nature not in natures_deja_vues, natures_dans_l_ordre_de_la_liste
            natures_deja_vues.append(nature)

        # Une phrase d'aide par nature présente dans le plan.
        # / One help sentence per nature present in the plan.
        natures_du_plan = set(
            CompteComptable.objects.values_list("nature_du_compte", flat=True)
        )
        for nature in natures_du_plan:
            aides_de_la_nature = textes_des_elements(contenu, f"aide-nature-{nature}")
            assert len(aides_de_la_nature) == 1, nature
            assert aides_de_la_nature[0] != "", nature

        aide_des_ventes = textes_des_elements(
            contenu, f"aide-nature-{CompteComptable.VENTE}"
        )[0]
        assert "association" in aide_des_ventes.lower(), aide_des_ventes
        for numero in ["754", "756", "706", "707"]:
            assert numero in aide_des_ventes, (numero, aide_des_ventes)

    def test_comptes_des_monnaies_liste_les_monnaies_acceptees(self):
        """L'écran « Comptes des monnaies » a une ligne par monnaie acceptée par le
        lieu, fedow_core ET ancien Fedow, avec son nom, son origine (« ce lieu », « un
        autre lieu », « fédérée ») et son compte. Une monnaie sans compte est
        signalée : « l'export comptable sera refusé tant que ce compte manque ». Une
        monnaie que le lieu n'accepte pas n'a pas de ligne.
        / One row per currency accepted by the venue (both engines), with name,
        origin and account; a currency without account is flagged; a currency the
        venue does not accept has no row."""
        # Acceptées : les monnaies du lieu (deux moteurs), deux monnaies d'un autre
        # lieu fédérées avec lui (avec et sans compte), le FED de l'ancien Fedow.
        # / Accepted: the venue's currencies, two federated ones, the old-Fedow FED.
        monnaie_fedow_core_du_lieu = _monnaie_fedow_core(self.tenant)
        monnaie_ancien_fedow_du_lieu = _monnaie_ancien_fedow(self.tenant)
        compte_de_la_monnaie_du_lieu = _creer_un_compte(
            "419200", "Monnaie locale du lieu", CompteComptable.TIERS
        )
        MappingMonnaie.objects.create(
            asset_uuid=monnaie_ancien_fedow_du_lieu.uuid,
            compte_de_tresorerie=compte_de_la_monnaie_du_lieu,
        )

        monnaie_d_un_autre_lieu_sans_compte = (
            _monnaie_ancien_fedow_d_un_autre_lieu_acceptee_ici(self.tenant)
        )
        monnaie_d_un_autre_lieu_avec_compte = (
            _monnaie_ancien_fedow_d_un_autre_lieu_acceptee_ici(self.tenant)
        )
        compte_de_la_monnaie_federee = _creer_un_compte(
            "467100", "Monnaie d'un autre lieu", CompteComptable.TIERS
        )
        MappingMonnaie.objects.create(
            asset_uuid=monnaie_d_un_autre_lieu_avec_compte.uuid,
            compte_de_tresorerie=compte_de_la_monnaie_federee,
        )

        fed_de_l_ancien_fedow = AssetFedowPublic.objects.filter(
            category=AssetFedowPublic.STRIPE_FED_FIAT
        ).first()
        if fed_de_l_ancien_fedow is None:
            fed_de_l_ancien_fedow = _monnaie_ancien_fedow(
                _un_autre_lieu(), categorie=AssetFedowPublic.STRIPE_FED_FIAT
            )
        # Le chargeur relie le FED au 467000 s'il n'a pas encore de compte.
        # / The loader links the FED to 467000 if it has no account yet.
        charger_le_plan_comptable_par_defaut()

        # Non acceptées : les monnaies d'un autre lieu, sans fédération.
        # / Not accepted: another venue's currencies, without federation.
        monnaie_fedow_core_non_acceptee = _monnaie_fedow_core(_un_autre_lieu())
        monnaie_ancien_fedow_non_acceptee = _monnaie_ancien_fedow(_un_autre_lieu())

        navigateur, _administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)
        reponse = navigateur.get(
            reverse("staff_admin:laboutik_mappingmonnaie_changelist")
        )

        assert reponse.status_code == 200
        contenu = reponse.content.decode()

        # (monnaie, origine attendue, numéro de compte attendu ou None)
        # / (currency, expected origin, expected account number or None)
        lignes_attendues = [
            (monnaie_fedow_core_du_lieu, gettext("ce lieu"), None),
            (monnaie_ancien_fedow_du_lieu, gettext("ce lieu"), "419200"),
            (monnaie_d_un_autre_lieu_sans_compte, gettext("un autre lieu"), None),
            (monnaie_d_un_autre_lieu_avec_compte, gettext("un autre lieu"), "467100"),
            (fed_de_l_ancien_fedow, gettext("fédérée"), "467000"),
        ]
        for monnaie, origine_attendue, numero_attendu in lignes_attendues:
            lignes_de_la_monnaie = textes_des_elements(
                contenu, f"monnaie-{monnaie.uuid}"
            )
            assert len(lignes_de_la_monnaie) == 1, (
                f"La monnaie « {monnaie.name} » doit avoir une ligne, trouvé "
                f"{len(lignes_de_la_monnaie)}."
            )
            texte_de_la_ligne = lignes_de_la_monnaie[0]
            assert monnaie.name in texte_de_la_ligne, texte_de_la_ligne
            assert origine_attendue.lower() in texte_de_la_ligne.lower(), (
                origine_attendue,
                texte_de_la_ligne,
            )
            if numero_attendu is not None:
                assert numero_attendu in texte_de_la_ligne, texte_de_la_ligne
                alertes = textes_des_elements(
                    contenu, f"monnaie-sans-compte-{monnaie.uuid}"
                )
                assert alertes == [], (monnaie.name, alertes)

        # La monnaie d'un autre lieu sans compte est signalée.
        # / The other venue's currency without account is flagged.
        alertes_de_la_monnaie_sans_compte = textes_des_elements(
            contenu, f"monnaie-sans-compte-{monnaie_d_un_autre_lieu_sans_compte.uuid}"
        )
        assert len(alertes_de_la_monnaie_sans_compte) == 1
        assert (
            gettext(PHRASE_D_UNE_MONNAIE_SANS_COMPTE).lower()
            in alertes_de_la_monnaie_sans_compte[0].lower()
        ), alertes_de_la_monnaie_sans_compte[0]

        # Les monnaies non acceptées n'ont pas de ligne.
        # / Currencies not accepted have no row.
        for monnaie_non_acceptee in [
            monnaie_fedow_core_non_acceptee,
            monnaie_ancien_fedow_non_acceptee,
        ]:
            assert (
                textes_des_elements(contenu, f"monnaie-{monnaie_non_acceptee.uuid}")
                == []
            ), monnaie_non_acceptee.name

    def test_comptes_des_monnaies_orange_seulement_pour_une_monnaie_d_ailleurs(self):
        """Une monnaie DU LIEU sans compte propre n'est pas en orange : l'écran
        indique en neutre le compte du moyen utilisé (419100, fiche §3.1). Une
        monnaie fédérée (FED) sans compte est en orange : l'export la refuse.
        / A venue currency without its own account is not flagged: the screen shows
        the method account used (419100). A federated currency (FED) without account
        is flagged: the export refuses it."""
        monnaie_fedow_core_du_lieu = _monnaie_fedow_core(self.tenant)
        monnaie_ancien_fedow_du_lieu = _monnaie_ancien_fedow(self.tenant)

        fed_de_l_ancien_fedow = AssetFedowPublic.objects.filter(
            category=AssetFedowPublic.STRIPE_FED_FIAT
        ).first()
        if fed_de_l_ancien_fedow is None:
            fed_de_l_ancien_fedow = _monnaie_ancien_fedow(
                _un_autre_lieu(), categorie=AssetFedowPublic.STRIPE_FED_FIAT
            )
        MappingMonnaie.objects.filter(asset_uuid=fed_de_l_ancien_fedow.uuid).delete()

        navigateur, _administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)
        reponse = navigateur.get(
            reverse("staff_admin:laboutik_mappingmonnaie_changelist")
        )
        assert reponse.status_code == 200
        contenu = reponse.content.decode()

        for monnaie_du_lieu in [monnaie_fedow_core_du_lieu, monnaie_ancien_fedow_du_lieu]:
            lignes = textes_des_elements(contenu, f"monnaie-{monnaie_du_lieu.uuid}")
            assert len(lignes) == 1, monnaie_du_lieu.name
            assert "419100" in lignes[0], lignes[0]
            alertes = textes_des_elements(
                contenu, f"monnaie-sans-compte-{monnaie_du_lieu.uuid}"
            )
            assert alertes == [], (monnaie_du_lieu.name, alertes)

        alertes_du_fed = textes_des_elements(
            contenu, f"monnaie-sans-compte-{fed_de_l_ancien_fedow.uuid}"
        )
        assert len(alertes_du_fed) == 1, alertes_du_fed
        assert (
            gettext(PHRASE_D_UNE_MONNAIE_SANS_COMPTE).lower()
            in alertes_du_fed[0].lower()
        ), alertes_du_fed[0]

    def test_comptes_des_monnaies_sans_archivees_ni_monnaies_sans_argent(self):
        """Pas de ligne pour une monnaie archivée, ni pour une monnaie sans écriture
        d'argent (points, temps, adhésion, badge), dans les deux moteurs. Une monnaie
        cadeau (TNF) est de l'argent : elle a sa ligne.
        / No row for an archived currency, nor for a non-money currency, in both
        engines. A gift currency (TNF) is money: it has its row."""
        monnaies_sans_ligne = []

        monnaie_ancien_fedow_archivee = _monnaie_ancien_fedow(self.tenant)
        monnaie_ancien_fedow_archivee.archive = True
        monnaie_ancien_fedow_archivee.save()
        monnaies_sans_ligne.append(monnaie_ancien_fedow_archivee)

        monnaie_fedow_core_archivee = _monnaie_fedow_core(self.tenant)
        monnaie_fedow_core_archivee.archive = True
        monnaie_fedow_core_archivee.save()
        monnaies_sans_ligne.append(monnaie_fedow_core_archivee)

        for categorie_sans_argent in [
            AssetFedowPublic.FIDELITY,
            AssetFedowPublic.TIME,
            AssetFedowPublic.SUBSCRIPTION,
            AssetFedowPublic.BADGE,
        ]:
            monnaies_sans_ligne.append(
                _monnaie_ancien_fedow(self.tenant, categorie=categorie_sans_argent)
            )
        for categorie_sans_argent in [Asset.FID, Asset.TIM]:
            monnaies_sans_ligne.append(
                _monnaie_fedow_core(self.tenant, categorie=categorie_sans_argent)
            )

        monnaie_cadeau_du_lieu = _monnaie_ancien_fedow(
            self.tenant, categorie=AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT
        )

        navigateur, _administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)
        reponse = navigateur.get(
            reverse("staff_admin:laboutik_mappingmonnaie_changelist")
        )
        assert reponse.status_code == 200
        contenu = reponse.content.decode()

        for monnaie_sans_ligne in monnaies_sans_ligne:
            assert (
                textes_des_elements(contenu, f"monnaie-{monnaie_sans_ligne.uuid}")
                == []
            ), (monnaie_sans_ligne.name, monnaie_sans_ligne.category)
        assert (
            len(textes_des_elements(contenu, f"monnaie-{monnaie_cadeau_du_lieu.uuid}"))
            == 1
        )

    def test_comptes_des_monnaies_formulaire_ne_propose_que_tresorerie_et_tiers(self):
        """Le formulaire du compte d'une monnaie ne propose que des comptes de
        trésorerie ou de tiers.
        / The currency account form only offers treasury or third-party accounts."""
        _navigateur, administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)
        admin_des_comptes_des_monnaies = staff_admin_site._registry[MappingMonnaie]
        requete = RequestFactory().get(
            reverse("staff_admin:laboutik_mappingmonnaie_add")
        )
        requete.user = administrateur

        formulaire = admin_des_comptes_des_monnaies.get_form(requete)
        comptes_proposes = formulaire.base_fields["compte_de_tresorerie"].queryset

        natures_proposees = set(
            comptes_proposes.values_list("nature_du_compte", flat=True)
        )
        assert natures_proposees <= {
            CompteComptable.TRESORERIE,
            CompteComptable.TIERS,
        }, natures_proposees
        numeros_proposes = set(
            comptes_proposes.values_list("numero_de_compte", flat=True)
        )
        assert {"530000", "512000", "419100", "467000"} <= numeros_proposes
        for numero_refuse in ["707000", "445711", "623400", "758000"]:
            assert numero_refuse not in numeros_proposes, numero_refuse

    def test_code_journal_dans_le_formulaire_du_point_de_vente(self):
        """Le formulaire du point de vente montre le champ « code journal » avec son
        aide, à la création comme à la modification (valeur reprise).
        / The point of sale form shows the journal code field with its help, on
        creation and on edit (value shown)."""
        navigateur, administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)

        # L'aide du champ, telle que l'admin la construit.
        # / The field's help, as the admin builds it.
        admin_des_points_de_vente = staff_admin_site._registry[PointDeVente]
        requete = RequestFactory().get(reverse("staff_admin:laboutik_pointdevente_add"))
        requete.user = administrateur
        formulaire = admin_des_points_de_vente.get_form(requete)
        aide_du_code_journal = str(formulaire.base_fields["code_journal"].help_text)
        assert aide_du_code_journal.strip() != ""

        reponse = navigateur.get(reverse("staff_admin:laboutik_pointdevente_add"))
        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        assert 'name="code_journal"' in contenu
        assert aide_du_code_journal in contenu

        bar = _point_de_vente("Bar formulaire", code_journal="BARFORM")
        reponse = navigateur.get(
            reverse("staff_admin:laboutik_pointdevente_change", args=[bar.pk])
        )
        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        assert 'name="code_journal"' in contenu
        assert 'value="BARFORM"' in contenu

    def test_prix_d_achat_aide_en_centimes_par_unite(self):
        """L'aide du prix d'achat dit : en centimes, par unité de vente (kg, litre,
        pièce) ; 0 = inconnu (D21).
        / The purchase price help says: in cents, per sale unit; 0 = unknown."""
        aide_du_prix_d_achat = str(Product._meta.get_field("prix_achat").help_text)

        assert (
            "en centimes, par unité de vente (kg, litre, pièce)"
            in aide_du_prix_d_achat.lower()
        ), aide_du_prix_d_achat
        assert "0 = inconnu" in aide_du_prix_d_achat.lower(), aide_du_prix_d_achat

    # ------------------------------------------------------------------ #
    #  « Plan complet ? » / "Complete plan?"                              #
    # ------------------------------------------------------------------ #

    def test_plan_complet_appelle_le_filet(self):
        """« Plan complet ? » charge d'abord le plan si le lieu n'a aucun compte.
        / "Complete plan?" first loads the plan if the venue has no account."""
        _vider_le_plan_du_lieu()

        manques = _ce_qui_manque_pour_exporter()

        numeros_presents = set(
            CompteComptable.objects.values_list("numero_de_compte", flat=True)
        )
        assert numeros_presents == NUMEROS_DU_PLAN_PAR_DEFAUT
        assert manques == [], _phrases_des_manques(manques)

    def test_plan_complet_n_est_pas_calcule_a_l_ouverture_des_trois_ecrans(self):
        """« Plan complet ? » relit tout l'historique du lieu : il n'est pas calculé
        à l'ouverture des trois écrans du plan. Chaque écran porte le bouton
        « Vérifier le plan » (`data-testid="plan-complet-verifier"`), et aucun verdict
        (ni manque, ni message vert) tant qu'on ne l'a pas cliqué. Un manque existe
        pourtant (chèque sans compte).
        / "Complete plan?" is not computed when the three screens open: each
        carries the "Check the plan" button and no verdict until it is clicked."""
        _preparer_la_caisse()
        MappingMoyenDePaiement.objects.filter(moyen_de_paiement="CH").delete()
        _vendre(_biere_rangee_au_bar(), moyen="CH")
        navigateur, _administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)
        libelle_attendu = texte_sans_espaces_en_trop(gettext("Vérifier le plan"))

        # Les deux noms sous lesquels la fonction peut être appelée : celui du module
        # du plan, et celui importé par l'admin (`create=True` : l'admin peut ne plus
        # l'importer).
        # / The two names the function can be called by: the plan module's, and the
        # one imported by the admin (create=True: the admin may no longer import it).
        with (
            patch(
                "laboutik.plan_comptable.ce_qui_manque_pour_exporter",
                return_value=[],
            ) as plan_complet_du_module,
            patch(
                "Administration.admin.laboutik.ce_qui_manque_pour_exporter",
                return_value=[],
                create=True,
            ) as plan_complet_de_l_admin,
        ):
            for nom_de_l_ecran in NOMS_DES_TROIS_ECRANS_DU_PLAN:
                reponse = navigateur.get(reverse(nom_de_l_ecran))
                assert reponse.status_code == 200, nom_de_l_ecran
                contenu = reponse.content.decode()

                boutons = textes_des_elements(contenu, "plan-complet-verifier")
                assert len(boutons) == 1, (nom_de_l_ecran, boutons)
                assert libelle_attendu in boutons[0], (nom_de_l_ecran, boutons[0])
                assert textes_des_elements(contenu, "plan-complet-manque") == [], (
                    nom_de_l_ecran
                )
                assert textes_des_elements(contenu, "plan-complet-ok") == [], (
                    nom_de_l_ecran
                )

        assert plan_complet_du_module.call_count == 0
        assert plan_complet_de_l_admin.call_count == 0

    def test_ouvrir_un_ecran_du_plan_charge_le_plan_d_un_lieu_neuf(self):
        """Un lieu sans aucun compte ouvre l'un des trois écrans du plan : le filet
        (`s_assurer_que_le_plan_existe`) charge le plan par défaut à l'ouverture,
        même si le calcul des manques reste derrière le bouton « Vérifier le plan ».
        / A venue without any account opens a plan screen: the safety net loads the
        default plan."""
        navigateur, _administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)
        for nom_de_l_ecran in NOMS_DES_TROIS_ECRANS_DU_PLAN:
            _vider_le_plan_du_lieu()
            assert not CompteComptable.objects.exists()

            reponse = navigateur.get(reverse(nom_de_l_ecran))

            assert reponse.status_code == 200, nom_de_l_ecran
            numeros_presents = set(
                CompteComptable.objects.values_list("numero_de_compte", flat=True)
            )
            assert numeros_presents == NUMEROS_DU_PLAN_PAR_DEFAUT, nom_de_l_ecran

    def test_verifier_le_plan_refuse_un_utilisateur_qui_n_est_pas_admin_du_lieu(self):
        """Un utilisateur connecté qui n'est pas administrateur du lieu demande le
        verdict de « Plan complet ? » : refusé (le site d'admin le renvoie vers la
        connexion), aucun verdict n'est rendu.
        / A non-admin user asking for the verdict is refused; no verdict rendered."""
        email_du_visiteur = f"visiteur-{identifiant_unique()}@tibillet.localhost"
        visiteur = TibilletUser.objects.create(
            email=email_du_visiteur, username=email_du_visiteur, is_active=True
        )
        navigateur = TenantClient(self.tenant)
        navigateur.force_login(visiteur)

        reponse = navigateur.get(
            reverse("staff_admin:laboutik_comptecomptable_verifier_le_plan"),
            HTTP_HX_REQUEST="true",
        )

        assert reponse.status_code in (302, 403), reponse.status_code
        contenu = reponse.content.decode()
        assert 'data-testid="plan-complet-ok"' not in contenu
        assert 'data-testid="plan-complet-manque"' not in contenu

    def test_plan_complet_rien_a_signaler_message_vert(self):
        """Un lieu au plan complet, avec des ventes réglées qui ont toutes un compte
        (dont un règlement dans la monnaie du lieu sans compte propre : repli sur le
        moyen, fiche §3.1) : aucun manque. Le bouton « Vérifier le plan » de chacun
        des trois écrans du plan rend le message vert.
        / A complete plan with settled sales that all have an account: nothing
        missing; the "Check the plan" button of the three screens gives the green
        message."""
        _preparer_la_caisse()
        biere = _biere_rangee_au_bar()
        _vendre(biere, moyen="CA")
        monnaie_du_lieu_sans_compte_propre = _monnaie_fedow_core(self.tenant)
        _vendre(biere, moyen="LE", asset=monnaie_du_lieu_sans_compte_propre.uuid)

        manques = _ce_qui_manque_pour_exporter()

        assert manques == [], _phrases_des_manques(manques)

        navigateur, _administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)
        message_attendu = texte_sans_espaces_en_trop(gettext(MESSAGE_DU_PLAN_COMPLET))
        for nom_de_l_ecran in NOMS_DES_TROIS_ECRANS_DU_PLAN:
            reponse = navigateur.get(reverse(nom_de_l_ecran))
            assert reponse.status_code == 200, nom_de_l_ecran
            contenu = _verdict_du_bouton_verifier_le_plan(
                navigateur, reponse.content.decode()
            )

            messages_verts = textes_des_elements(contenu, "plan-complet-ok")
            assert len(messages_verts) == 1, nom_de_l_ecran
            assert message_attendu in messages_verts[0], (
                nom_de_l_ecran,
                messages_verts[0],
            )
            assert textes_des_elements(contenu, "plan-complet-manque") == [], (
                nom_de_l_ecran
            )

    def test_plan_complet_affiche_les_manques_en_tete_des_trois_ecrans(self):
        """Un manque est affiché par le bouton « Vérifier le plan » de chacun des
        trois écrans du plan, sans message vert.
        / The "Check the plan" button of the three plan screens shows a missing item,
        without green message."""
        _preparer_la_caisse()
        MappingMoyenDePaiement.objects.filter(moyen_de_paiement="CH").delete()
        _vendre(_biere_rangee_au_bar(), moyen="CH")
        manques = _ce_qui_manque_pour_exporter()
        assert len(manques) == 1, _phrases_des_manques(manques)
        phrase_du_manque = texte_sans_espaces_en_trop(manques[0]["phrase"])

        navigateur, _administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)
        for nom_de_l_ecran in NOMS_DES_TROIS_ECRANS_DU_PLAN:
            reponse = navigateur.get(reverse(nom_de_l_ecran))
            assert reponse.status_code == 200, nom_de_l_ecran
            contenu = _verdict_du_bouton_verifier_le_plan(
                navigateur, reponse.content.decode()
            )

            manques_affiches = textes_des_elements(contenu, "plan-complet-manque")
            assert len(manques_affiches) == 1, (nom_de_l_ecran, manques_affiches)
            assert phrase_du_manque in manques_affiches[0], (
                nom_de_l_ecran,
                manques_affiches[0],
            )
            assert textes_des_elements(contenu, "plan-complet-ok") == [], (
                nom_de_l_ecran
            )

    def test_plan_complet_collision_et_nom_sans_lettre_listes_ensemble(self):
        """Une collision de codes journal ET un point de vente au nom sans lettre :
        « Plan complet ? » liste les deux. Le nom sans lettre ne cache pas la
        collision des autres points de vente.
        / A journal code collision AND a point of sale named without letters: both
        are listed; the letterless name does not hide the others' collision."""
        _point_de_vente("123")
        _point_de_vente("Buvette du haut", code_journal="BUVETTE")
        _point_de_vente("Buvette")

        manques = _ce_qui_manque_pour_exporter()

        phrases = _phrases_des_manques(manques)
        assert len(manques) == 2, phrases
        manques_de_la_collision = []
        manques_du_nom_sans_lettre = []
        for phrase in phrases:
            if "BUVETTE" in phrase:
                manques_de_la_collision.append(phrase)
            if "123" in phrase:
                manques_du_nom_sans_lettre.append(phrase)
        assert len(manques_de_la_collision) == 1, phrases
        assert len(manques_du_nom_sans_lettre) == 1, phrases

    def test_collisions_de_codes_journal_ignore_un_nom_sans_lettre(self):
        """`collisions_de_codes_journal` ne lève plus sur un point de vente sans
        code au nom sans lettre : elle le saute, et la collision des autres reste
        signalée. `points_de_vente_sans_code_journal` les rend à part.
        / The collision function skips a letterless point of sale; the others'
        collision is still reported; the letterless ones are returned apart."""
        from laboutik.plan_comptable import points_de_vente_sans_code_journal

        point_de_vente_sans_lettre = _point_de_vente("123")
        _point_de_vente("Buvette du haut", code_journal="BUVETTE")
        _point_de_vente("Buvette")

        collisions = collisions_de_codes_journal()

        assert list(collisions.keys()) == ["BUVETTE"]
        assert points_de_vente_sans_code_journal() == [point_de_vente_sans_lettre]

    def test_plan_complet_tva_zero_sans_compte_de_tva(self):
        """Une ligne à TVA 0 % n'exige pas de compte de TVA : pas de manque.
        / A 0 % VAT line requires no VAT account: nothing missing."""
        _preparer_la_caisse()
        assert not CompteComptable.objects.filter(
            nature_du_compte=CompteComptable.TVA, taux_de_tva=Decimal("0.00")
        ).exists()
        _vendre(_biere_rangee_au_bar(), taux_tva="0")

        manques = _ce_qui_manque_pour_exporter()

        assert manques == [], _phrases_des_manques(manques)

    def test_plan_complet_meme_produit_vendu_dans_deux_monnaies_un_seul_manque(self):
        """Un produit sans compte vendu en euros ET dans la monnaie du lieu (deux
        lignes de monnaies différentes) : un seul manque, pas un par monnaie.
        / A product without account sold in euros AND in the venue currency: a single
        missing item, not one per currency."""
        _preparer_la_caisse()
        planche = creer_tarif_vendu(nom="Planche deux monnaies", methode_caisse=Product.VENTE)
        monnaie_du_lieu = _monnaie_fedow_core(self.tenant)

        _vendre(planche, moyen="CA")
        vente_en_monnaie_locale = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE
        )
        ajouter_article(
            vente_en_monnaie_locale,
            pricesold=planche,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("20"),
            asset=monnaie_du_lieu.uuid,
        )
        ajouter_reglement(
            vente_en_monnaie_locale, moyen="LE", montant=500, asset=monnaie_du_lieu.uuid
        )
        encaisser_vente(vente_en_monnaie_locale)

        manques = _ce_qui_manque_pour_exporter()

        phrases = _phrases_des_manques(manques)
        assert len(manques) == 1, phrases
        assert planche.productsold.product.name in phrases[0], phrases

    def test_plan_complet_signale_ce_qui_manque(self):
        """Chaque sorte de manque, une par une (chacune seule, annulée avant la
        suivante) : un seul manque, avec une phrase qui nomme la chose et un lien vers
        l'écran qui le règle. « Utilisé » = présent dans les ventes RÉGLÉES.
        / Each kind of missing item, one at a time: a single missing item, whose
        sentence names the thing, with a link to the screen that fixes it."""
        _preparer_la_caisse()
        lien_du_plan = reverse("staff_admin:laboutik_comptecomptable_changelist")
        lien_des_moyens = reverse(
            "staff_admin:laboutik_mappingmoyendepaiement_changelist"
        )
        lien_des_monnaies = reverse("staff_admin:laboutik_mappingmonnaie_changelist")
        lien_des_points_de_vente = reverse(
            "staff_admin:laboutik_pointdevente_changelist"
        )

        # Au départ, rien ne manque.
        # / At the start, nothing is missing.
        manques_au_depart = _ce_qui_manque_pour_exporter()
        assert manques_au_depart == [], _phrases_des_manques(manques_au_depart)

        def un_seul_manque(nom_du_cas):
            manques = _ce_qui_manque_pour_exporter()
            assert len(manques) == 1, f"{nom_du_cas} : {_phrases_des_manques(manques)}"
            return manques[0]

        # --- 1. Produit vendu sans compte / Product sold without account ---
        # Vendu deux fois : un seul manque. Un produit sans compte dans une vente EN
        # ATTENTE ne compte pas.
        # / Sold twice: one missing item. A pending sale does not count.
        def cas_produit_vendu_sans_compte():
            planche = creer_tarif_vendu(
                nom="Planche apéro", methode_caisse=Product.VENTE
            )
            _vendre(planche)
            _vendre(planche)
            tapas_en_attente = creer_tarif_vendu(
                nom="Tapas en attente", methode_caisse=Product.VENTE
            )
            vente_en_attente = ouvrir_vente(
                origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE
            )
            ajouter_article(
                vente_en_attente,
                pricesold=tapas_en_attente,
                quantite=Decimal("1"),
                prix_unitaire=500,
                taux_tva=Decimal("20"),
            )

            manque = un_seul_manque("produit")
            assert planche.productsold.product.name in manque["phrase"], manque
            assert manque["lien"].startswith("/admin/"), manque

        # --- 2. Moyen utilisé sans compte / Method used without account ---
        # Le virement (TR) perd aussi sa correspondance, mais il n'est pas utilisé.
        # / TR also loses its mapping, but it is not used.
        def cas_moyen_utilise_sans_compte():
            MappingMoyenDePaiement.objects.filter(
                moyen_de_paiement__in=["CH", "TR"]
            ).delete()
            _vendre(_biere_rangee_au_bar(), moyen="CH")

            manque = un_seul_manque("moyen")
            le_moyen_est_nomme = (
                "CH" in manque["phrase"]
                or str(PaymentMethod.CHEQUE.label) in manque["phrase"]
            )
            assert le_moyen_est_nomme, manque
            assert manque["lien"].startswith(lien_des_moyens), manque

        # --- 3. Monnaie utilisée sans compte / Currency used without account ---
        # La monnaie du lieu sans compte propre prend celui du moyen (fiche §3.1) :
        # pas de manque. Une monnaie acceptée mais pas utilisée : pas de manque.
        # / The venue's currency falls back to the method: no missing item. An
        # accepted but unused currency: no missing item.
        def cas_monnaie_utilisee_sans_compte():
            biere = _biere_rangee_au_bar()
            monnaie_d_un_autre_lieu = (
                _monnaie_ancien_fedow_d_un_autre_lieu_acceptee_ici(self.tenant)
            )
            _vendre(biere, moyen="LE", asset=monnaie_d_un_autre_lieu.uuid)
            monnaie_du_lieu = _monnaie_fedow_core(self.tenant)
            _vendre(biere, moyen="LE", asset=monnaie_du_lieu.uuid)
            _monnaie_ancien_fedow_d_un_autre_lieu_acceptee_ici(self.tenant)

            manque = un_seul_manque("monnaie")
            assert monnaie_d_un_autre_lieu.name in manque["phrase"], manque
            assert manque["lien"].startswith(lien_des_monnaies), manque

        # --- 4. Taux de TVA utilisé sans compte / VAT rate used without account ---
        # Le compte à 2,1 % disparaît aussi, mais aucune vente n'est à 2,1 %.
        # / The 2.1 % account goes too, but no sale is at 2.1 %.
        def cas_taux_de_tva_utilise_sans_compte():
            _compte("445713").delete()
            _compte("445714").delete()
            _vendre(_biere_rangee_au_bar(), taux_tva="5.50")

            manque = un_seul_manque("TVA")
            le_taux_est_nomme = "5,5" in manque["phrase"] or "5.5" in manque["phrase"]
            assert le_taux_est_nomme, manque
            assert manque["lien"].startswith(lien_du_plan), manque

        # --- 5. Collision de codes journal / Journal code collision ---
        def cas_collision_de_codes_journal():
            _point_de_vente("Buvette du haut", code_journal="BUVETTE")
            _point_de_vente("Buvette")
            _point_de_vente("Cuisine", code_journal="CUISINE")

            manque = un_seul_manque("collision")
            assert "BUVETTE" in manque["phrase"], manque
            assert manque["lien"].startswith(lien_des_points_de_vente), manque

        # --- 6. Point de vente sans code, au nom sans lettre ---
        # `collisions_de_codes_journal` lève une erreur : « Plan complet ? »
        # l'attrape et la montre comme un manque, sans planter.
        # / Point of sale without code, named without letters: the error is caught
        # and shown as a missing item, without crashing.
        def cas_point_de_vente_au_nom_sans_lettre():
            _point_de_vente("123")

            manque = un_seul_manque("nom sans lettre")
            assert "123" in manque["phrase"], manque
            assert manque["lien"].startswith(lien_des_points_de_vente), manque

        # --- 7. Règlements au compte d'attente 471000 / Payments to suspense ---
        def cas_reglements_au_compte_d_attente():
            biere = _biere_rangee_au_bar()
            _vendre(biere, moyen="UK")
            _vendre(biere, moyen="UK")

            # En français : la phrase est comparée à un mot français (« reclasser »).
            # / In French: the sentence is compared to a French word.
            with translation.override("fr"):
                manque = un_seul_manque("471000")
            assert "2" in manque["phrase"], manque
            assert "reclasser" in manque["phrase"].lower(), manque
            # Le lien mène à la liste des ventes, filtrée sur le moyen inconnu.
            # / The link leads to the sales list, filtered on the unknown method.
            assert manque["lien"] == (
                reverse("staff_admin:BaseBillet_vente_changelist") + "?moyen=UK"
            ), manque

        cas_a_verifier = [
            cas_produit_vendu_sans_compte,
            cas_moyen_utilise_sans_compte,
            cas_monnaie_utilisee_sans_compte,
            cas_taux_de_tva_utilise_sans_compte,
            cas_collision_de_codes_journal,
            cas_point_de_vente_au_nom_sans_lettre,
            cas_reglements_au_compte_d_attente,
        ]
        for verifier_le_cas in cas_a_verifier:
            # Chaque cas est annulé avant le suivant : un seul manque à la fois.
            # / Each case is rolled back before the next: one missing item at a time.
            point_de_sauvegarde = transaction.savepoint()
            try:
                verifier_le_cas()
            finally:
                transaction.savepoint_rollback(point_de_sauvegarde)

    # ------------------------------------------------------------------ #
    #  « Plan complet ? » : corrections de la relecture (E-4)             #
    #  "Complete plan?": review fixes                                     #
    # ------------------------------------------------------------------ #

    def test_plan_complet_nombre_de_requetes_ne_grandit_pas(self):
        """« Plan complet ? » s'affiche à chaque ouverture des trois écrans du plan :
        son nombre de requêtes ne grandit pas avec le nombre de produits vendus. Même
        nombre avec 2 et avec 12 produits vendus, chacun dans sa propre catégorie ou
        au compte du plan par défaut, payés en espèces ou par carte.
        / "Complete plan?" runs on every plan screen: its query count does not grow
        with the number of products sold. Same count with 2 and with 12 products."""
        _preparer_la_caisse()

        # Un produit sur deux est rangé dans sa propre catégorie (règle 2) et payé en
        # espèces ; l'autre est un billet de caisse sans catégorie (règle 3 : compte du
        # plan par défaut) payé par carte. Les deux runs ont donc les mêmes moyens.
        # / Every other product in its own category paid in cash; the other a POS
        # ticket without category (default plan account) paid by card.
        def vendre_les_produits(rang_du_premier, rang_apres_le_dernier):
            for rang in range(rang_du_premier, rang_apres_le_dernier):
                if rang % 2 == 0:
                    produit_range = creer_tarif_vendu(
                        nom=f"Produit rangé {rang}", methode_caisse=Product.VENTE
                    )
                    _ranger_dans_une_categorie(produit_range, _compte("707000"))
                    _vendre(produit_range, moyen="CA")
                else:
                    billet_de_caisse = creer_tarif_vendu(
                        nom=f"Billet de caisse {rang}", methode_caisse=Product.BILLET_POS
                    )
                    _vendre(billet_de_caisse, moyen="CC")

        def nombre_de_requetes_de_plan_complet():
            with CaptureQueriesContext(connection) as requetes_relevees:
                manques = _ce_qui_manque_pour_exporter()
            assert manques == [], _phrases_des_manques(manques)
            return len(requetes_relevees.captured_queries)

        vendre_les_produits(0, 2)
        # Un premier appel à blanc : les caches de Django (types de contenu…) ne
        # comptent pas dans la mesure.
        # / A first dry call: Django caches do not count in the measure.
        _ce_qui_manque_pour_exporter()
        requetes_avec_deux_produits = nombre_de_requetes_de_plan_complet()

        vendre_les_produits(2, 12)
        requetes_avec_douze_produits = nombre_de_requetes_de_plan_complet()

        assert requetes_avec_douze_produits == requetes_avec_deux_produits, (
            f"2 produits vendus : {requetes_avec_deux_produits} requêtes ; "
            f"12 produits vendus : {requetes_avec_douze_produits} requêtes."
        )

    def test_plan_complet_ignore_les_ventes_en_points(self):
        """Une vente en points n'a pas d'écriture comptable (fiche F §4) : un produit
        sans compte vendu SEULEMENT contre des points ne manque pas. Vendu en euros,
        il manque.
        / A points sale writes no accounting entry: a product without account sold
        ONLY for points is not missing. Sold in euros, it is."""
        _preparer_la_caisse()
        planche = creer_tarif_vendu(
            nom="Planche vendue en points", methode_caisse=Product.VENTE
        )
        points_de_fidelite = _monnaie_fedow_core(self.tenant, categorie=Asset.FID)

        # La vente en points : unité = la monnaie de points, TVA 0, règlement NM.
        # / The points sale: unit = the points currency, 0 VAT, NM payment.
        vente_en_points = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.VENTE,
            unite=str(points_de_fidelite.uuid),
        )
        ajouter_article(
            vente_en_points,
            pricesold=planche,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("0"),
            payment_method=PaymentMethod.NON_MONETAIRE,
            asset=points_de_fidelite.uuid,
        )
        ajouter_reglement(
            vente_en_points,
            moyen=PaymentMethod.NON_MONETAIRE,
            montant=500,
            asset=points_de_fidelite.uuid,
        )
        encaisser_vente(vente_en_points)

        manques_apres_la_vente_en_points = _ce_qui_manque_pour_exporter()
        assert manques_apres_la_vente_en_points == [], _phrases_des_manques(
            manques_apres_la_vente_en_points
        )

        _vendre(planche, moyen="CA")

        manques_apres_la_vente_en_euros = _ce_qui_manque_pour_exporter()
        phrases = _phrases_des_manques(manques_apres_la_vente_en_euros)
        assert len(phrases) == 1, phrases
        assert planche.productsold.product.name in phrases[0], phrases

    def test_plan_complet_compte_du_plan_par_defaut_supprime(self):
        """Le 707900 (ventes réglées en jetons) est supprimé, deux produits sont vendus
        en jetons cadeau (lignes LG) : UN seul manque, dont la phrase nomme le numéro
        qui manque et le bouton « Charger le plan par défaut » qui le remet ; le lien
        mène à l'écran du plan, pas à celui des catégories.
        / 707900 deleted, two products sold in gift tokens: ONE missing item naming the
        number and the "Load the default plan" button; the link goes to the plan."""
        _preparer_la_caisse()
        _compte("707900").delete()
        jetons_cadeau_du_lieu = _monnaie_fedow_core(self.tenant, categorie=Asset.TNF)
        _vendre_payee_en_jetons(_biere_rangee_au_bar(), jetons_cadeau_du_lieu)
        _vendre_payee_en_jetons(_biere_rangee_au_bar(), jetons_cadeau_du_lieu)

        manques = _ce_qui_manque_pour_exporter()

        phrases = _phrases_des_manques(manques)
        assert len(manques) == 1, phrases
        assert "707900" in phrases[0], phrases
        assert gettext("Charger le plan par défaut") in phrases[0], phrases
        lien_du_plan = reverse("staff_admin:laboutik_comptecomptable_changelist")
        assert manques[0]["lien"].startswith(lien_du_plan), manques[0]

    def test_plan_complet_lien_regler_porte_la_phrase_du_manque(self):
        """Le lien « Régler » de chaque manque dit au lecteur d'écran CE qu'il règle :
        son nom accessible (aria-label, ou texte caché) contient la phrase du manque.
        / Each "Fix" link tells the screen reader what it fixes: its accessible name
        contains the missing item's sentence."""
        _preparer_la_caisse()
        MappingMoyenDePaiement.objects.filter(moyen_de_paiement="CH").delete()
        _vendre(_biere_rangee_au_bar(), moyen="CH")
        manques = _ce_qui_manque_pour_exporter()
        assert len(manques) == 1, _phrases_des_manques(manques)
        phrase_du_manque = texte_sans_espaces_en_trop(manques[0]["phrase"])
        navigateur, _administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)

        reponse = navigateur.get(
            reverse("staff_admin:laboutik_comptecomptable_changelist")
        )

        assert reponse.status_code == 200
        verdict_du_plan = _verdict_du_bouton_verifier_le_plan(
            navigateur, reponse.content.decode()
        )
        noms_accessibles = _noms_accessibles_des_liens_des_manques(verdict_du_plan)
        assert len(noms_accessibles) == 1, noms_accessibles
        assert phrase_du_manque in noms_accessibles[0], noms_accessibles

    def test_plan_comptable_ordonne_par_nature_comme_l_aide(self):
        """La liste des comptes suit l'ordre des natures de la phrase d'aide de
        l'écran (ventes d'abord), pas l'ordre alphabétique des codes.
        / The account list follows the nature order of the screen's help (sales
        first), not the alphabetical order of the codes."""
        navigateur, _administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)

        reponse = navigateur.get(
            reverse("staff_admin:laboutik_comptecomptable_changelist")
        )

        assert reponse.status_code == 200
        contenu = reponse.content.decode()

        natures_dans_l_ordre_de_la_liste = []
        for compte in reponse.context["cl"].result_list:
            nature = compte.nature_du_compte
            if nature not in natures_dans_l_ordre_de_la_liste:
                natures_dans_l_ordre_de_la_liste.append(nature)

        # L'ordre de l'aide est lu dans la page : `aide-nature-<NATURE>`, de haut en
        # bas. Seules les natures présentes dans la liste comptent.
        # / The help order is read from the page, top to bottom.
        natures_dans_l_ordre_de_l_aide = re.findall(
            r'data-testid="aide-nature-([A-Z_]+)"', contenu
        )
        natures_attendues_dans_l_ordre = []
        for nature in natures_dans_l_ordre_de_l_aide:
            if nature in natures_dans_l_ordre_de_la_liste:
                natures_attendues_dans_l_ordre.append(nature)

        assert natures_dans_l_ordre_de_la_liste[0] == CompteComptable.VENTE, (
            natures_dans_l_ordre_de_la_liste
        )
        assert natures_dans_l_ordre_de_la_liste == natures_attendues_dans_l_ordre

    def test_code_journal_en_majuscules(self):
        """Un code journal posé en minuscules hors de l'admin (le validateur ne tourne
        que dans l'admin) sort en majuscules ; les collisions comparent les codes en
        majuscules : « bar » et « BAR » sont le même journal.
        / A lowercase journal code set outside the admin comes out uppercase;
        collisions compare uppercase codes: "bar" and "BAR" collide."""
        bar_en_minuscules = _point_de_vente("Bar en minuscules", code_journal="bar")

        assert code_journal_du_point_de_vente(bar_en_minuscules) == "BAR"
        assert journal_pour(bar_en_minuscules, SaleOrigin.LABOUTIK) == "BAR"

        bar_en_majuscules = _point_de_vente("Bar en majuscules", code_journal="BAR")

        collisions = collisions_de_codes_journal()
        assert "BAR" in collisions, list(collisions.keys())
        uuids_en_collision = set()
        for point_de_vente in collisions["BAR"]:
            uuids_en_collision.add(point_de_vente.uuid)
        assert uuids_en_collision == {bar_en_minuscules.uuid, bar_en_majuscules.uuid}

    def test_aide_du_numero_de_compte_six_chiffres(self):
        """L'aide du numéro de compte donne en exemple des numéros à 6 chiffres, comme
        ceux du plan par défaut.
        / The account number help gives 6-digit examples, like the default plan."""
        aide_du_numero = str(
            CompteComptable._meta.get_field("numero_de_compte").help_text
        )

        numeros_en_exemple = re.findall(r"\d{4,}", aide_du_numero)

        assert numeros_en_exemple != [], aide_du_numero
        for numero_en_exemple in numeros_en_exemple:
            assert len(numero_en_exemple) == 6, aide_du_numero

    # ------------------------------------------------------------------ #
    #  Le formulaire du compte d'une monnaie / The currency account form   #
    # ------------------------------------------------------------------ #

    def test_formulaire_monnaie_propose_les_monnaies_acceptees(self):
        """La liste du formulaire propose les monnaies acceptées par le lieu, des deux
        moteurs (fedow_core et ancien Fedow) ; pas une monnaie d'un autre lieu que le
        lieu n'accepte pas.
        / The form lists the currencies the venue accepts, both engines; not another
        venue's currency the venue does not accept."""
        monnaie_fedow_core_du_lieu = _monnaie_fedow_core(self.tenant)
        monnaie_ancien_fedow_du_lieu = _monnaie_ancien_fedow(self.tenant)
        monnaie_federee_acceptee = _monnaie_ancien_fedow_d_un_autre_lieu_acceptee_ici(
            self.tenant
        )
        monnaie_fedow_core_non_acceptee = _monnaie_fedow_core(_un_autre_lieu())
        monnaie_ancien_fedow_non_acceptee = _monnaie_ancien_fedow(_un_autre_lieu())

        formulaire = MappingMonnaieForm()

        uuids_proposes = set()
        for valeur, _libelle in formulaire.fields["asset_uuid"].widget.choices:
            uuids_proposes.add(str(valeur))
        for monnaie_acceptee in [
            monnaie_fedow_core_du_lieu,
            monnaie_ancien_fedow_du_lieu,
            monnaie_federee_acceptee,
        ]:
            assert str(monnaie_acceptee.uuid) in uuids_proposes, monnaie_acceptee.name
        for monnaie_non_acceptee in [
            monnaie_fedow_core_non_acceptee,
            monnaie_ancien_fedow_non_acceptee,
        ]:
            assert str(monnaie_non_acceptee.uuid) not in uuids_proposes, (
                monnaie_non_acceptee.name
            )

    def test_formulaire_monnaie_correspondance_existante_garde_sa_monnaie(self):
        """Une correspondance existante garde sa monnaie dans la liste, même si le lieu
        ne l'accepte plus : elle reste modifiable.
        / An existing mapping keeps its currency in the list even if no longer
        accepted: it stays editable."""
        monnaie_plus_acceptee = _monnaie_ancien_fedow(_un_autre_lieu())
        correspondance_existante = MappingMonnaie.objects.create(
            asset_uuid=monnaie_plus_acceptee.uuid,
            compte_de_tresorerie=_compte("467000"),
        )

        formulaire = MappingMonnaieForm(
            data={
                "asset_uuid": str(monnaie_plus_acceptee.uuid),
                "compte_de_tresorerie": _compte("419100").pk,
            },
            instance=correspondance_existante,
        )

        uuids_proposes = set()
        for valeur, _libelle in formulaire.fields["asset_uuid"].widget.choices:
            uuids_proposes.add(str(valeur))
        assert str(monnaie_plus_acceptee.uuid) in uuids_proposes
        assert formulaire.is_valid(), formulaire.errors

    def test_formulaire_monnaie_non_acceptee_refusee(self):
        """Une monnaie que le lieu n'accepte pas est refusée, avec une phrase pour un
        bénévole.
        / A currency the venue does not accept is refused, with a plain sentence."""
        monnaie_non_acceptee = _monnaie_ancien_fedow(_un_autre_lieu())

        formulaire = MappingMonnaieForm(
            data={
                "asset_uuid": str(monnaie_non_acceptee.uuid),
                "compte_de_tresorerie": _compte("467000").pk,
            }
        )

        assert not formulaire.is_valid()
        assert formulaire.errors["asset_uuid"] == [
            gettext("Choisissez une monnaie acceptée par le lieu.")
        ], formulaire.errors

    def test_formulaire_monnaie_doublon_phrase_falc(self):
        """Choisir une monnaie qui a déjà son compte donne une phrase pour un bénévole,
        pas le message de Django (« … already exists »).
        / Picking a currency that already has its account gives a plain sentence, not
        Django's "already exists" message."""
        monnaie_du_lieu = _monnaie_fedow_core(self.tenant)
        MappingMonnaie.objects.create(
            asset_uuid=monnaie_du_lieu.uuid,
            compte_de_tresorerie=_compte("419100"),
        )

        formulaire = MappingMonnaieForm(
            data={
                "asset_uuid": str(monnaie_du_lieu.uuid),
                "compte_de_tresorerie": _compte("467000").pk,
            }
        )

        assert not formulaire.is_valid()
        assert formulaire.errors["asset_uuid"] == [
            gettext("Cette monnaie a déjà son compte : modifiez la ligne existante.")
        ], formulaire.errors

    def test_ecran_choisir_un_compte_pre_rempli_par_la_monnaie(self):
        """Le lien « Choisir un compte » de l'écran des monnaies ouvre la page d'ajout
        avec `?asset_uuid=` : la monnaie y est déjà choisie.
        / The "Choose an account" link opens the add page with ?asset_uuid=: the
        currency is already selected."""
        monnaie_du_lieu = _monnaie_fedow_core(self.tenant)
        navigateur, _administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)

        reponse = navigateur.get(
            reverse("staff_admin:laboutik_mappingmonnaie_add")
            + f"?asset_uuid={monnaie_du_lieu.uuid}"
        )

        assert reponse.status_code == 200
        formulaire_de_la_page = reponse.context["adminform"].form
        assert str(formulaire_de_la_page["asset_uuid"].value()) == str(
            monnaie_du_lieu.uuid
        )
        option_choisie = re.search(
            rf'<option value="{monnaie_du_lieu.uuid}"[^>]*\bselected\b',
            reponse.content.decode(),
        )
        assert option_choisie is not None

    # ------------------------------------------------------------------ #
    #  Couverture : règles du plan / Coverage: plan rules                 #
    # ------------------------------------------------------------------ #

    def test_compte_pour_reglement_jetons_cadeau_du_lieu_et_d_un_autre_lieu(self):
        """Des jetons cadeau (LG) dans la monnaie cadeau du lieu, sans compte propre :
        le compte du moyen LG, 419100. Les jetons cadeau d'un autre lieu, sans compte :
        erreur (un compte par monnaie), dans les deux moteurs.
        / Gift tokens (LG) in the venue's gift currency: 419100. Another venue's gift
        tokens without account: error, both engines."""
        jetons_du_lieu = _monnaie_fedow_core(self.tenant, categorie=Asset.TNF)
        assert compte_pour_reglement("LG", jetons_du_lieu.uuid).numero_de_compte == (
            "419100"
        )

        jetons_fedow_core_d_un_autre_lieu = _monnaie_fedow_core(
            _un_autre_lieu(), categorie=Asset.TNF
        )
        jetons_ancien_fedow_d_un_autre_lieu = _monnaie_ancien_fedow(
            _un_autre_lieu(), categorie=AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT
        )
        for jetons_d_un_autre_lieu in [
            jetons_fedow_core_d_un_autre_lieu,
            jetons_ancien_fedow_d_un_autre_lieu,
        ]:
            with self.assertRaises(CompteComptableManquant) as erreur:
                compte_pour_reglement("LG", jetons_d_un_autre_lieu.uuid)
            assert str(jetons_d_un_autre_lieu.uuid) in str(erreur.exception)

    def test_virement_recu_dont_la_monnaie_n_a_pas_de_compte_erreur(self):
        """Le virement du pot central (VR) va au compte de sa monnaie : une monnaie
        sans compte, ou une ligne sans monnaie, lève une erreur qui nomme le virement.
        / The central pot transfer (VR) goes to its currency's account: a currency
        without account, or no currency, raises naming the transfer."""
        virement_recu = creer_tarif_vendu(
            nom="Virement sans compte", methode_caisse=Product.VIREMENT_RECU
        )
        monnaie_sans_compte = _monnaie_ancien_fedow(_un_autre_lieu())
        nom_du_virement = virement_recu.productsold.product.name

        for monnaie_de_la_ligne in [monnaie_sans_compte.uuid, None]:
            ligne = _ligne_d_article(
                virement_recu, hors_chiffre_affaires=True, asset=monnaie_de_la_ligne
            )
            with self.assertRaises(CompteComptableManquant) as erreur:
                compte_pour_article(ligne)
            assert nom_du_virement in str(erreur.exception), monnaie_de_la_ligne

    def test_nom_de_la_monnaie_ancien_fedow_puis_uuid_inconnu(self):
        """Le nom d'une monnaie : celui de l'ancien Fedow quand elle n'est pas dans
        fedow_core ; l'uuid en texte quand elle n'est nulle part.
        / A currency's name: the old Fedow one when not in fedow_core; the uuid as text
        when nowhere."""
        monnaie_ancien_fedow = _monnaie_ancien_fedow(self.tenant)
        uuid_inconnu = uuid.uuid4()

        assert nom_de_la_monnaie(monnaie_ancien_fedow.uuid) == monnaie_ancien_fedow.name
        assert nom_de_la_monnaie(uuid_inconnu) == str(uuid_inconnu)

    def test_plan_complet_une_monnaie_et_un_moyen_signales_une_seule_fois(self):
        """Une monnaie sans compte utilisée par deux moyens, et un moyen sans compte
        utilisé avec deux monnaies : un seul manque pour la monnaie, un seul pour le
        moyen.
        / A currency without account used by two methods, and a method without account
        used with two currencies: one missing item each."""
        _preparer_la_caisse()
        biere = _biere_rangee_au_bar()

        # Le moyen LE perd son compte ; deux monnaies du lieu le prennent (repli).
        # / LE loses its account; two venue currencies use it (fallback).
        MappingMoyenDePaiement.objects.filter(moyen_de_paiement="LE").delete()
        _vendre(biere, moyen="LE", asset=_monnaie_fedow_core(self.tenant).uuid)
        _vendre(biere, moyen="LE", asset=_monnaie_ancien_fedow(self.tenant).uuid)

        # Une monnaie d'un autre lieu sans compte, payée par deux moyens.
        # / Another venue's currency without account, paid by two methods.
        monnaie_d_un_autre_lieu = _monnaie_ancien_fedow_d_un_autre_lieu_acceptee_ici(
            self.tenant
        )
        _vendre(biere, moyen="LE", asset=monnaie_d_un_autre_lieu.uuid)
        _vendre(biere, moyen="LG", asset=monnaie_d_un_autre_lieu.uuid)

        manques = _ce_qui_manque_pour_exporter()

        phrases = _phrases_des_manques(manques)
        assert len(manques) == 2, phrases
        phrases_de_la_monnaie = []
        phrases_du_moyen = []
        for phrase in phrases:
            if monnaie_d_un_autre_lieu.name in phrase:
                phrases_de_la_monnaie.append(phrase)
            if "(LE)" in phrase:
                phrases_du_moyen.append(phrase)
        assert len(phrases_de_la_monnaie) == 1, phrases
        assert len(phrases_du_moyen) == 1, phrases

    def test_chargeur_sur_l_ancien_plan_bar_resto_a_sept_chiffres(self):
        """Un lieu garde l'ancien plan « bar_resto » (numéros à 7 et 8 chiffres, TVA à
        d'autres numéros). Le chargeur ajoute les comptes à 6 chiffres qui manquent, ne
        renumérote ni ne modifie aucun ancien compte, ne touche aucune ancienne
        correspondance, et ne double aucun taux de TVA : un seul compte par taux.
        / A venue keeps the old "bar_resto" plan. The loader adds the missing 6-digit
        accounts, renumbers and changes nothing, keeps the old mappings, and never
        doubles a VAT rate."""
        _vider_le_plan_du_lieu()

        # L'ancien plan « bar_resto », recopié de l'ancienne commande
        # `charger_plan_comptable --jeu=bar_resto` : (numéro, libellé, nature, taux).
        # / The old "bar_resto" plan, copied from the old command.
        ancien_plan_bar_resto = [
            ("7072000", "Boissons a 20%", CompteComptable.VENTE, "20.00"),
            ("7071000", "Boissons a 10%", CompteComptable.VENTE, "10.00"),
            ("7011000", "Alimentaire a 10%", CompteComptable.VENTE, "10.00"),
            ("7010500", "Alimentaire a emporter 5,5%", CompteComptable.VENTE, "5.50"),
            ("51120001", "Paiement CB", CompteComptable.TRESORERIE, None),
            ("5300000", "Paiement Especes", CompteComptable.TRESORERIE, None),
            ("51120002", "Paiement Tickets Restaurants", CompteComptable.TRESORERIE, None),
            ("51120000", "Paiement en cheque", CompteComptable.TRESORERIE, None),
            ("445712", "TVA 20%", CompteComptable.TVA, "20.00"),
            ("445710", "TVA 10%", CompteComptable.TVA, "10.00"),
            ("445705", "TVA 5,5%", CompteComptable.TVA, "5.50"),
            ("709000", "Remises", CompteComptable.SPECIAL, None),
            ("5811000", "Caisse (mouvements especes)", CompteComptable.SPECIAL, None),
            ("758000", "Ecart de gestion +", CompteComptable.PRODUIT_EXCEPTIONNEL, None),
            ("658000", "Ecart de gestion -", CompteComptable.CHARGE, None),
            ("41910000", "Avances clients (cashless)", CompteComptable.TIERS, None),
        ]
        for numero, libelle, nature, taux in ancien_plan_bar_resto:
            taux_du_compte = None
            if taux is not None:
                taux_du_compte = Decimal(taux)
            CompteComptable.objects.create(
                numero_de_compte=numero,
                libelle_du_compte=libelle,
                nature_du_compte=nature,
                taux_de_tva=taux_du_compte,
            )

        # Ses anciennes correspondances (None : moyen ignoré, compte vide).
        # / Its old mappings (None: ignored method, empty account).
        anciennes_correspondances = {
            "CA": "5300000",
            "CC": "51120001",
            "CH": "51120000",
            "LE": "41910000",
            "LG": None,
            "QR": "51120001",
            "SN": "51120001",
            "SF": None,
            "NA": None,
        }
        for moyen, numero in anciennes_correspondances.items():
            compte_du_moyen = None
            if numero is not None:
                compte_du_moyen = _compte(numero)
            MappingMoyenDePaiement.objects.create(
                moyen_de_paiement=moyen,
                libelle_moyen=f"Ancien {moyen}",
                compte_de_tresorerie=compte_du_moyen,
            )

        avertissements = charger_le_plan_comptable_par_defaut()

        assert avertissements == [], avertissements

        # Aucun ancien compte renuméroté ni modifié.
        # / No old account renumbered or changed.
        for numero, libelle, nature, taux in ancien_plan_bar_resto:
            compte_ancien = _compte(numero)
            assert compte_ancien.libelle_du_compte == libelle, numero
            assert compte_ancien.nature_du_compte == nature, numero

        # Les comptes à 6 chiffres du plan qui manquaient sont ajoutés ; la TVA, elle,
        # est cherchée par taux.
        # / The missing 6-digit plan accounts are added; VAT is looked up by rate.
        numeros_presents = set(
            CompteComptable.objects.values_list("numero_de_compte", flat=True)
        )
        for numero, nature in NATURE_ATTENDUE_PAR_NUMERO.items():
            if nature == CompteComptable.TVA:
                continue
            assert numero in numeros_presents, numero

        # Un seul compte de TVA par taux : les anciens pour 20 / 10 / 5,5 %, le plan
        # pour 2,1 % (absent de l'ancien plan).
        # / One VAT account per rate: the old ones for 20 / 10 / 5.5 %, the plan's
        # for 2.1 %.
        numero_de_tva_attendu_par_taux = {
            Decimal("20.00"): "445712",
            Decimal("10.00"): "445710",
            Decimal("5.50"): "445705",
            Decimal("2.10"): "445714",
        }
        for taux, numero_attendu in numero_de_tva_attendu_par_taux.items():
            comptes_de_ce_taux = CompteComptable.objects.filter(
                nature_du_compte=CompteComptable.TVA, taux_de_tva=taux
            )
            assert comptes_de_ce_taux.count() == 1, taux
            assert comptes_de_ce_taux.get().numero_de_compte == numero_attendu, taux
        assert not CompteComptable.objects.filter(numero_de_compte="445711").exists()

        # Les anciennes correspondances restent ; les moyens qui n'en avaient pas en
        # reçoivent une.
        # / Old mappings stay; methods without one get one.
        for moyen, numero in anciennes_correspondances.items():
            correspondance = MappingMoyenDePaiement.objects.get(moyen_de_paiement=moyen)
            if numero is None:
                assert correspondance.compte_de_tresorerie is None, moyen
            else:
                assert correspondance.compte_de_tresorerie.numero_de_compte == numero, (
                    moyen
                )
        for moyen in ["TR", "SP", "SR", "UK"]:
            correspondance = MappingMoyenDePaiement.objects.get(moyen_de_paiement=moyen)
            assert (
                correspondance.compte_de_tresorerie.numero_de_compte
                == COMPTE_ATTENDU_PAR_MOYEN[moyen]
            ), moyen

    # ------------------------------------------------------------------ #
    #  Couverture : vidage de jetons cadeau d'un autre lieu               #
    #  Coverage: emptying another venue's gift tokens                      #
    # ------------------------------------------------------------------ #

    def test_vidage_jetons_cadeau_d_un_autre_lieu_reglement_lg_sans_compte(self):
        """Une carte porte, sur l'ancien Fedow, 1,50 € de jetons cadeau d'un AUTRE
        lieu. Le caissier la vide (vraie route de la caisse, ancien Fedow simulé).
        - La vente du vidage est écrite et réglée : un règlement « jetons » (LG) +150,
          dans cette monnaie.
        - Le plan n'a pas de compte pour cette monnaie : `compte_pour_reglement` refuse
          (l'export serait refusé), et « Plan complet ? » la signale.
        / A card holds 1.50 € of ANOTHER venue's gift tokens on the old Fedow; the
        cashier empties it. The sale is written (LG +150 in that currency);
        compte_pour_reglement refuses it and "Complete plan?" flags it."""
        _preparer_la_caisse()
        jetons_d_un_autre_lieu = _monnaie_ancien_fedow(
            _un_autre_lieu(), categorie=AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT
        )

        # La caisse : un point de vente, la carte primaire du caissier (autorisée sur
        # ce point de vente), la carte du client. 8 caractères au plus (PIEGES 9.31).
        # / The register: a point of sale, the cashier's primary card, the card.
        point_de_vente = _point_de_vente("Comptoir vidage plan unique")
        identifiant_de_la_carte_primaire = identifiant_unique().upper()
        carte_du_caissier = CarteCashless.objects.create(
            tag_id=identifiant_de_la_carte_primaire,
            number=identifiant_de_la_carte_primaire,
            uuid=uuid.uuid4(),
        )
        carte_primaire = CartePrimaire.objects.create(
            carte=carte_du_caissier, edit_mode=False
        )
        carte_primaire.points_de_vente.add(point_de_vente)
        identifiant_de_la_carte_du_client = identifiant_unique().upper()
        carte_du_client = CarteCashless.objects.create(
            tag_id=identifiant_de_la_carte_du_client,
            number=identifiant_de_la_carte_du_client,
            uuid=uuid.uuid4(),
        )

        # L'ancien Fedow, simulé : il connaît la carte, et son vidage reprend les
        # jetons de l'autre lieu (catégorie lue dans le portefeuille d'avant le
        # vidage, comme le vrai serveur la rend).
        # / The old Fedow, faked: its refund takes back the other venue's tokens.
        faux_ancien_fedow = MagicMock()
        faux_ancien_fedow.NFCcard.refund.return_value = {
            "serialized_transactions": [
                {
                    "uuid": uuid.uuid4(),
                    "asset": jetons_d_un_autre_lieu.uuid,
                    "amount": 150,
                }
            ],
            "before_refund_serialized_wallet": {
                "tokens": [
                    {
                        "asset_uuid": jetons_d_un_autre_lieu.uuid,
                        "asset_category": "TNF",
                        "asset_name": jetons_d_un_autre_lieu.name,
                    }
                ]
            },
        }

        navigateur, _administrateur = _navigateur_d_un_admin_du_lieu(self.tenant)
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with taches_celery_enregistrees():
                with patch.object(FedowConfig, "can_fedow", return_value=True):
                    with patch(
                        "laboutik.views.FedowAPI", return_value=faux_ancien_fedow
                    ):
                        reponse = navigateur.post(
                            "/laboutik/paiement/vider_carte/",
                            {
                                "tag_id": carte_du_client.tag_id,
                                "tag_id_cm": carte_du_caissier.tag_id,
                                "uuid_pv": str(point_de_vente.uuid),
                                "vider_carte": "false",
                            },
                        )

        assert reponse.status_code == 200, reponse.content.decode()[:400]
        vente_du_vidage = Vente.objects.get(
            nature=Vente.Nature.VIDAGE_CARTE, carte=carte_du_client
        )
        assert vente_du_vidage.statut == Vente.Statut.REGLEE
        reglements_en_jetons = []
        for reglement in Reglement.objects.filter(
            vente=vente_du_vidage, moyen=PaymentMethod.LOCAL_GIFT
        ):
            reglements_en_jetons.append((reglement.montant, str(reglement.asset)))
        assert reglements_en_jetons == [(150, str(jetons_d_un_autre_lieu.uuid))]

        with self.assertRaises(CompteComptableManquant):
            compte_pour_reglement("LG", jetons_d_un_autre_lieu.uuid)

        manques = _ce_qui_manque_pour_exporter()
        phrases = _phrases_des_manques(manques)
        assert len(manques) == 1, phrases
        assert jetons_d_un_autre_lieu.name in phrases[0], phrases
        assert manques[0]["lien"].startswith(
            reverse("staff_admin:laboutik_mappingmonnaie_changelist")
        ), manques[0]

    # ------------------------------------------------------------------ #
    #  Couverture : le service de vente (avoirs) / Sale service guards    #
    # ------------------------------------------------------------------ #

    def test_recharge_fed_en_ligne_hors_chiffre_affaires(self):
        """Une recharge FED en ligne (type de produit `E`) n'est jamais une vente : le
        service de vente la marque hors chiffre d'affaires, comme la recharge `R`.
        / An online FED top-up (type E) is never a sale: marked off revenue, like R."""
        _preparer_la_caisse()
        recharge_fed = creer_tarif_vendu(
            nom="Recharge FED en ligne",
            categorie_article=Product.RECHARGE_CASHLESS_FED,
        )
        vente_en_ligne = ouvrir_vente(
            origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE
        )

        ligne = ajouter_article(
            vente_en_ligne,
            pricesold=recharge_fed,
            quantite=Decimal("1"),
            prix_unitaire=1000,
            taux_tva=Decimal("0"),
        )

        ligne.refresh_from_db()
        assert ligne.hors_chiffre_affaires is True

    def test_article_d_avoir_hors_d_une_vente_avoir_refuse(self):
        """Un article d'avoir va dans une vente AVOIR : dans une vente ordinaire, refus.
        / A credit note item goes into an AVOIR sale: refused in an ordinary sale."""
        _preparer_la_caisse()
        vente_reglee = _vendre(_biere_rangee_au_bar())
        ligne_vendue = vente_reglee.articles.get()
        vente_ordinaire = ouvrir_vente(
            origine=SaleOrigin.ADMIN, nature=Vente.Nature.VENTE
        )

        with self.assertRaises(ValueError):
            ajouter_l_article_d_avoir(vente_ordinaire, ligne_vendue, Decimal("1"))

        assert not LigneArticle.objects.filter(vente=vente_ordinaire).exists()

    def test_article_d_avoir_quantite_hors_bornes_refusee(self):
        """La quantité rendue doit être positive et au plus la quantité vendue : 0, −1
        et la quantité vendue + 1 sont refusées.
        / The quantity given back must be positive and at most the sold one."""
        _preparer_la_caisse()
        vente_reglee = _vendre(_biere_rangee_au_bar())
        ligne_vendue = vente_reglee.articles.get()
        vente_avoir = ouvrir_vente(origine=SaleOrigin.ADMIN, nature=Vente.Nature.AVOIR)

        for quantite_refusee in [
            Decimal("0"),
            Decimal("-1"),
            ligne_vendue.qty + Decimal("1"),
        ]:
            with self.assertRaises(ValueError):
                ajouter_l_article_d_avoir(vente_avoir, ligne_vendue, quantite_refusee)

        assert not LigneArticle.objects.filter(vente=vente_avoir).exists()

    def test_article_d_avoir_recopie_les_metadonnees_de_la_ligne_d_origine(self):
        """L'article d'avoir recopie les métadonnées de la ligne d'origine et y ajoute
        son uuid ; la ligne d'origine garde les siennes, intactes.
        / The credit note item copies the original line's metadata and adds its uuid;
        the original line keeps its own, untouched."""
        _preparer_la_caisse()
        biere = _biere_rangee_au_bar()
        vente = ouvrir_vente(origine=SaleOrigin.ADMIN, nature=Vente.Nature.VENTE)
        ligne_vendue = ajouter_article(
            vente,
            pricesold=biere,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("20"),
            metadata={"reference_du_lieu": "table 4"},
        )
        ajouter_reglement(vente, moyen=PaymentMethod.CASH, montant=500)
        encaisser_vente(vente)
        vente_avoir = ouvrir_vente(origine=SaleOrigin.ADMIN, nature=Vente.Nature.AVOIR)

        article_d_avoir = ajouter_l_article_d_avoir(
            vente_avoir, ligne_vendue, Decimal("1")
        )

        assert article_d_avoir.metadata == {
            "reference_du_lieu": "table 4",
            "original_lignearticle_uuid": str(ligne_vendue.uuid),
        }
        ligne_vendue.refresh_from_db()
        assert ligne_vendue.metadata == {"reference_du_lieu": "table 4"}

    def test_avoir_vente_d_origine_pas_reglee_refuse_par_le_service(self):
        """La fonction commune des avoirs refuse une ligne dont la vente n'est pas
        réglée ; rien n'est écrit.
        / The common credit note function refuses a line whose sale is not settled."""
        _preparer_la_caisse()
        vente_en_attente = ouvrir_vente(
            origine=SaleOrigin.ADMIN, nature=Vente.Nature.VENTE
        )
        ligne_d_une_vente_en_attente = ajouter_article(
            vente_en_attente,
            pricesold=_biere_rangee_au_bar(),
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("20"),
            payment_method=PaymentMethod.CASH,
            status=LigneArticle.VALID,
        )

        with self.assertRaises(ValueError):
            ecrire_la_vente_d_avoir_d_une_ligne(
                ligne_d_une_vente_en_attente,
                quantite=Decimal("1"),
                moyen_rembourse=PaymentMethod.CASH,
                origine=SaleOrigin.ADMIN,
            )

        assert not LigneArticle.objects.filter(
            credit_note_for=ligne_d_une_vente_en_attente
        ).exists()
        assert not Vente.objects.filter(nature=Vente.Nature.AVOIR).exists()

    def test_avoir_argent_a_rendre_sans_moyen_refuse_par_le_service(self):
        """De l'argent est à rendre (ligne en espèces) et aucun moyen « Remboursé par »
        n'est donné : refus, rien n'est écrit.
        / Money to give back and no "Refunded by" method: refused, nothing written."""
        _preparer_la_caisse()
        biere = _biere_rangee_au_bar()
        vente = ouvrir_vente(origine=SaleOrigin.ADMIN, nature=Vente.Nature.VENTE)
        ligne_en_especes = ajouter_article(
            vente,
            pricesold=biere,
            quantite=Decimal("1"),
            prix_unitaire=500,
            taux_tva=Decimal("20"),
            payment_method=PaymentMethod.CASH,
            status=LigneArticle.VALID,
        )
        ajouter_reglement(vente, moyen=PaymentMethod.CASH, montant=500)
        encaisser_vente(vente)
        # Relue en base : l'objet rendu par `ajouter_article` garde sa vente « en
        # attente » en mémoire, et la fonction des avoirs lit `ligne.vente.statut`.
        # / Read back: the in-memory line still holds its pending sale.
        ligne_en_especes = LigneArticle.objects.get(pk=ligne_en_especes.pk)

        with self.assertRaises(ValueError) as erreur:
            ecrire_la_vente_d_avoir_d_une_ligne(
                ligne_en_especes,
                quantite=Decimal("1"),
                moyen_rembourse=None,
                origine=SaleOrigin.ADMIN,
            )

        # Le refus vient de la garde du moyen, pas d'un refus plus loin (un règlement
        # au moyen vide serait refusé lui aussi, avec un autre message).
        # / The refusal comes from the method guard, not from a later refusal.
        assert "Remboursé par" in str(erreur.exception), str(erreur.exception)
        assert not LigneArticle.objects.filter(credit_note_for=ligne_en_especes).exists()
        assert not Vente.objects.filter(nature=Vente.Nature.AVOIR).exists()

    def test_avoir_d_une_ancienne_ligne_lg_sans_monnaie_ni_carte(self):
        """Une ligne payée en jetons cadeau (LG), écrite avant le chantier : sans vente,
        sans monnaie ni carte. Son avoir écrit un règlement « jetons » NÉGATIF, lui
        aussi sans monnaie ni carte ; la vente AVOIR tient ses deux égalités.
        / A pre-chantier LG line without sale, currency or card: its credit note writes
        a negative LG payment without currency or card; both equalities hold."""
        _preparer_la_caisse()
        # ÉTAT DE DÉPART : `create()` direct, comme les lignes d'avant le chantier.
        # / STARTING STATE: direct create(), like pre-chantier lines.
        ancienne_ligne_en_jetons = LigneArticle.objects.create(
            pricesold=_biere_rangee_au_bar(),
            qty=1,
            amount=300,
            vat=Decimal("0"),
            payment_method=PaymentMethod.LOCAL_GIFT,
            sale_origin=SaleOrigin.LABOUTIK,
            status=LigneArticle.VALID,
        )
        assert ancienne_ligne_en_jetons.vente_id is None
        assert ancienne_ligne_en_jetons.asset is None
        assert ancienne_ligne_en_jetons.carte_id is None

        with taches_celery_enregistrees():
            article_d_avoir = ecrire_la_vente_d_avoir_d_une_ligne(
                ancienne_ligne_en_jetons,
                quantite=Decimal("1"),
                moyen_rembourse=None,
                origine=SaleOrigin.ADMIN,
            )

        vente_d_avoir = Vente.objects.get(pk=article_d_avoir.vente_id)
        assert vente_d_avoir.statut == Vente.Statut.REGLEE
        reglements = list(Reglement.objects.filter(vente=vente_d_avoir))
        assert len(reglements) == 1
        assert reglements[0].moyen == PaymentMethod.LOCAL_GIFT
        assert reglements[0].montant == -300
        assert reglements[0].asset is None
        assert reglements[0].carte_id is None
        verifier_egalites(vente_d_avoir)

    # ------------------------------------------------------------------ #
    #  Couverture : le remboursement Stripe / Stripe refund guards        #
    # ------------------------------------------------------------------ #

    def test_remboursement_stripe_quantite_zero_refusee(self):
        """Une quantité imposée à 0 ne rembourse rien : refus, Stripe jamais appelé,
        aucune vente AVOIR.
        / A forced quantity of 0: refused, Stripe never called, no AVOIR sale."""
        _preparer_la_caisse()
        achat = _vendre_en_ligne_un_article_paye_par_stripe()

        with patch.object(
            Paiement_stripe, "get_checkout_session", side_effect=Exception("pas de session")
        ):
            with patch(
                "stripe.Refund.create", side_effect=_rembourser_comme_stripe
            ) as appels:
                with self.assertRaises(ValueError):
                    partial_refund_payment(
                        achat.paiement,
                        _configuration_stripe_du_test(),
                        [achat.ligne],
                        specified_quantity=0,
                    )

        assert appels.call_count == 0
        assert not _ventes_avoir_du_paiement(achat.paiement).exists()

    def test_remboursement_stripe_ligne_d_un_autre_paiement_refusee(self):
        """Une ligne qui n'appartient pas au paiement remboursé : refus, Stripe jamais
        appelé, aucune vente AVOIR.
        / A line that does not belong to the refunded payment: refused."""
        _preparer_la_caisse()
        premier_achat = _vendre_en_ligne_un_article_paye_par_stripe()
        second_achat = _vendre_en_ligne_un_article_paye_par_stripe()

        with patch.object(
            Paiement_stripe, "get_checkout_session", side_effect=Exception("pas de session")
        ):
            with patch(
                "stripe.Refund.create", side_effect=_rembourser_comme_stripe
            ) as appels:
                with self.assertRaises(ValueError):
                    partial_refund_payment(
                        premier_achat.paiement,
                        _configuration_stripe_du_test(),
                        [second_achat.ligne],
                    )

        assert appels.call_count == 0
        assert not _ventes_avoir_du_paiement(premier_achat.paiement).exists()
        assert not _ventes_avoir_du_paiement(second_achat.paiement).exists()

    def test_remboursement_stripe_ligne_non_remboursable_sautee(self):
        """Une ligne du paiement qui n'est ni VALID ni PAID (ici CREATED) n'est pas
        remboursée : Stripe n'est pas appelé, aucune vente AVOIR n'est ouverte.
        / A line neither VALID nor PAID is skipped: no Stripe call, no AVOIR sale."""
        _preparer_la_caisse()
        achat = _vendre_en_ligne_un_article_paye_par_stripe()
        LigneArticle.objects.filter(pk=achat.ligne.pk).update(
            status=LigneArticle.CREATED
        )
        achat.ligne.refresh_from_db()

        with patch.object(
            Paiement_stripe, "get_checkout_session", side_effect=Exception("pas de session")
        ):
            with patch(
                "stripe.Refund.create", side_effect=_rembourser_comme_stripe
            ) as appels:
                partial_refund_payment(
                    achat.paiement, _configuration_stripe_du_test(), [achat.ligne]
                )

        assert appels.call_count == 0
        assert not _ventes_avoir_du_paiement(achat.paiement).exists()
        assert not LigneArticle.objects.filter(credit_note_for=achat.ligne).exists()

    def test_remboursement_stripe_part_offerte_jamais_tracee_deux_fois(self):
        """Un paiement Stripe porte une ligne entièrement offerte (moyen historique
        « offert », 2 × 5 €). Deux remboursements partiels d'une unité chacun : chaque
        vente AVOIR a UN seul règlement « offert » de −500 (la règle « offert » du
        service l'a déjà écrit, le remboursement ne le réécrit pas) ; aucun appel à
        Stripe (rien d'argent à rendre) ; les égalités tiennent.
        / A Stripe payment carries a fully offered line (FREE, 2 × 5 €). Two partial
        refunds of one unit: each AVOIR sale has ONE −500 FREE payment, no Stripe call,
        equalities hold."""
        _preparer_la_caisse()
        vente_et_paiement = _vente_en_ligne_ouverte_avec_son_paiement_stripe()
        tarif_vendu = creer_tarif_vendu(nom="Entrée offerte", prix_en_euros="5.00")
        # La règle « offert » du service écrit elle-même le règlement offert de 1000.
        # / The service's "offered" rule writes the 1000 FREE payment itself.
        ligne_offerte = ajouter_article(
            vente_et_paiement.vente,
            pricesold=tarif_vendu,
            quantite=Decimal("2"),
            prix_unitaire=500,
            taux_tva=Decimal("20"),
            payment_method=PaymentMethod.FREE,
            paiement_stripe=vente_et_paiement.paiement,
            status=LigneArticle.VALID,
        )
        encaisser_vente(vente_et_paiement.vente)

        with taches_celery_enregistrees():
            with patch.object(
                Paiement_stripe,
                "get_checkout_session",
                side_effect=Exception("pas de session"),
            ):
                with patch(
                    "stripe.Refund.create", side_effect=_rembourser_comme_stripe
                ) as appels:
                    for _numero_du_remboursement in range(2):
                        partial_refund_payment(
                            vente_et_paiement.paiement,
                            _configuration_stripe_du_test(),
                            [LigneArticle.objects.get(pk=ligne_offerte.pk)],
                            specified_quantity=1,
                        )

        assert appels.call_count == 0
        ventes_avoir = list(_ventes_avoir_du_paiement(vente_et_paiement.paiement))
        assert len(ventes_avoir) == 2
        for vente_avoir in ventes_avoir:
            assert _moyens_et_montants(vente_avoir) == [(PaymentMethod.FREE, -500)]
            verifier_egalites(vente_avoir)

    def test_remboursement_stripe_refus_de_stripe_rien_n_est_ecrit(self):
        """Stripe refuse la demande (`InvalidRequestError`) : l'erreur remonte en
        ValueError, et rien n'est écrit (aucune vente AVOIR, aucune ligne négative, le
        paiement garde son statut).
        / Stripe refuses (InvalidRequestError): a ValueError is raised, nothing is
        written."""
        _preparer_la_caisse()
        achat = _vendre_en_ligne_un_article_paye_par_stripe()

        with patch.object(
            Paiement_stripe, "get_checkout_session", side_effect=Exception("pas de session")
        ):
            with patch(
                "stripe.Refund.create",
                side_effect=InvalidRequestError("Paiement inconnu (simulé).", None),
            ) as appels:
                with self.assertRaises(ValueError):
                    partial_refund_payment(
                        achat.paiement, _configuration_stripe_du_test(), [achat.ligne]
                    )

        assert appels.call_count == 1
        assert not _ventes_avoir_du_paiement(achat.paiement).exists()
        assert not LigneArticle.objects.filter(
            paiement_stripe=achat.paiement, qty__lt=0
        ).exists()
        achat.paiement.refresh_from_db()
        assert achat.paiement.status == Paiement_stripe.VALID
