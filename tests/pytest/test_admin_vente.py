"""
La fiche « Vente » de l'admin : une liste et une fiche, en lecture seule.
/ The admin "Sale" page: a list and a detail page, read-only.

LOCALISATION : tests/pytest/test_admin_vente.py

RÈGLE MÉTIER TESTÉE
Le back-office montre chaque `Vente` du lieu, toutes origines (caisse, en ligne, admin,
tireuse…), sans jamais permettre de la modifier : une vente réglée est scellée par son
empreinte.
- LA LISTE : numéro, date (heure du lieu), origine (libellé), point de vente, client
  (e-mail, ou numéro de carte), total, moyens (lus dans les règlements, libellés de
  `laboutik/affichage_des_ventes.py`), nature, statut. Filtres : origine, point de vente,
  moyen (une vente qui a un règlement de ce moyen), nature, statut, et « À vérifier ».
  Recherche : numéro, e-mail du client, carte. Nombre de requêtes constant.
- « À VÉRIFIER » : les ventes en attente depuis plus d'une heure (un encaissement
  en ligne en échec), et les ventes qui portent un article « Écart d'encaissement »
  (D26). Une vente en attente depuis 10 minutes n'y est pas.
- LA FICHE : en-tête, articles (produit, tarif, quantité, prix unitaire, offert,
  total, TVA), règlements (moyen, monnaie, montant, référence), vente liée et ventes
  dérivées (liens), badge d'intégrité : « Intégrité OK » quand l'empreinte recalculée
  (`calculer_hmac_vente`) est celle de la vente, « Intégrité KO » sinon.
- LECTURE SEULE : ajout, modification et suppression refusés.
- LE MENU « Ventes & comptabilité » : « Ventes » en premier, puis le rapport des
  ventes (clôtures), puis le plan comptable.
/ Read-only list and detail of every sale; "To check" filter; integrity badge; menu.

CONTRAT DE L'ÉCRAN (ce que ces tests supposent de l'interface)
- adresses : `/admin/BaseBillet/vente/` (liste), `/admin/BaseBillet/vente/<uuid>/change/`
  (fiche), `/admin/BaseBillet/vente/add/` (ajout, refusé) ;
- la liste rend sa `ChangeList` dans le contexte (`cl`, comme toute liste d'admin) ;
- paramètres des filtres : `a_verifier=oui`, `moyen=<code>`, `origine__exact`,
  `nature__exact`, `statut__exact`, `point_de_vente__uuid__exact` ; recherche : `q` ;
- fiche : le badge d'intégrité porte `data-testid="vente-integrite"` ; la vente liée et
  chaque vente dérivée sont des liens vers leur fiche ; un règlement qui porte une
  référence Stripe (remboursement `re_…`) a un lien vers le tableau de bord Stripe
  (`dashboard.stripe.com`, la référence dans l'adresse) ;
- action « Avoir total » : `/admin/BaseBillet/vente/<uuid>/avoir_total/`. GET = l'écran
  (200), avec un formulaire `form` dans le contexte ; il a le champ `moyen_rembourse`
  seulement s'il y a de l'argent à rendre hors Stripe. POST = l'avoir (302) ; un refus
  redirige (302) avec un message d'erreur, et rien n'est écrit ;
- action « Rejouer l'encaissement » : `/admin/BaseBillet/vente/<uuid>/rejouer_encaissement/`
  (POST, 302) ; un refus laisse un message d'erreur, rien n'est écrit.
/ Screen contract: addresses, the `cl` context, filter parameters, the integrity badge
testid, links to linked and derived sales and to Stripe; the "full credit note" and
"replay settlement" action addresses and their answers.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin
(tests/PIEGES.md 13.1). Les ventes sont écrites par le service de vente. Stripe et
Celery sont simulés. Le client de l'admin est créé dans chaque test, dans le lieu
(tests/PIEGES.md 13.10 : un client partagé perd sa session au premier rollback).
Chaque test retrouve SES ventes par la recherche (e-mail unique du client) : la base
de dev contient d'autres ventes.
/ Rolled back per test; sales through the service; a fresh admin client per test; each
test finds its own sales through the search (unique client e-mail).

D'OÙ VIENNENT LES VALEURS ATTENDUES
L'exemple fil rouge du chantier : 3 jus à 3,50 € payés 5,00 € en monnaie locale +
5,50 € par CB (deux parts), total 10,50 €. Libellés : ceux des choix des modèles,
dans la langue de la réponse.
/ The running example: 3 juices, 5.00 local + 5.50 CB, total 10.50.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-G-lecteurs.md (§4, §5
tests 14 et 16) ; brief CHANTIER-05-briefs/05-G-3.md (G-3c-1).

Lancer / Run : make test ARGS="tests/pytest/test_admin_vente.py"
"""

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib import messages
from django.contrib.messages import get_messages
from django.db import OperationalError, connection
from django.test import Client as DjangoClient
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone, translation
from django.utils.translation import gettext
from django_tenants.utils import tenant_context

from Administration.admin.dashboard import get_sidebar_navigation
from Administration.admin.site import staff_admin_site
from BaseBillet.models import (
    Configuration,
    LigneArticle,
    Paiement_stripe,
    PaymentMethod,
    Product,
    SaleOrigin,
)
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.services_vente import (
    ajouter_article,
    ajouter_l_article_d_ecart_d_encaissement,
    ajouter_reglement,
    ecrire_la_vente_d_avoir_d_une_ligne,
    ecrire_la_vente_d_avoir_d_une_vente,
    encaisser_vente,
    encaisser_vente_stripe,
    ouvrir_vente,
)
from comptabilite.presentation import euros_a_la_francaise
from fabriques_ecran import (
    LecteurDesLiens,
    textes_des_elements,
    texte_sans_espaces_en_trop,
)
from fabriques_panier import (
    catalogue_stripe_simule,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_vente import creer_tarif_vendu, verifier_egalites
from laboutik.models import LaboutikConfiguration, PointDeVente
from QrcodeCashless.models import CarteCashless
from test_caracterisation_annulations import (
    acheter_des_billets_payes_par_stripe,
    rembourser_comme_stripe,
)

pytestmark = pytest.mark.django_db

# Les adresses de la fiche « Vente » (contrat de l'écran).
# / The "Sale" page addresses (screen contract).
ADRESSE_DE_LA_LISTE_DES_VENTES = "/admin/BaseBillet/vente/"
ADRESSE_DE_L_AJOUT_D_UNE_VENTE = "/admin/BaseBillet/vente/add/"


def adresse_de_la_fiche(vente):
    """L'adresse de la fiche d'une vente. / A sale's detail page address."""
    return f"/admin/BaseBillet/vente/{vente.uuid}/change/"


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant, mock_stripe):
    """
    Le lieu `lespass`, avec Stripe (session, catalogue) et Celery simulés.
    / The `lespass` venue, with Stripe and Celery faked.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(tenant=tenant, taches_demandees=taches_demandees)


# --------------------------------------------------------------------------
# Outils
# / Helpers
# --------------------------------------------------------------------------


def client_de_l_admin_du_lieu(lieu):
    """
    Un administrateur du lieu, connecté, en français. Créé dans le test, dans le lieu
    (tests/PIEGES.md 13.10).
    / A logged-in venue admin, in French, created inside the test.
    """
    administrateur = creer_utilisateur(prenom="Admin", nom="Lieu")
    administrateur.client_admin.add(lieu.tenant)
    client = DjangoClient(
        HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="fr"
    )
    client.force_login(administrateur)
    client.administrateur = administrateur
    return client


def creer_un_point_de_vente():
    """Un point de vente caché (tests/PIEGES.md 9.41). / A hidden point of sale."""
    return PointDeVente.objects.create(
        name=f"TEST_admin_vente bar {identifiant_unique()}",
        comportement=PointDeVente.DIRECT,
        service_direct=True,
        accepte_especes=True,
        accepte_carte_bancaire=True,
        hidden=True,
    )


def vendre_trois_jus_en_deux_parts(client_de_la_vente, point_de_vente=None, carte=None):
    """
    Une vente de caisse réglée, au client donné : l'exemple fil rouge, 3 jus à 3,50 €
    payés 5,00 € en monnaie locale + 5,50 € par CB (deux parts). Rend la vente.
    / A settled register sale for the given customer: the running example.
    """
    tarif_du_jus = creer_tarif_vendu(nom="Jus", prix_en_euros="3.50")
    vente = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.VENTE,
        point_de_vente=point_de_vente,
        client=client_de_la_vente,
        carte=carte,
    )
    ajouter_article(
        vente,
        pricesold=tarif_du_jus,
        quantite=Decimal("1.428571"),
        prix_unitaire=350,
        taux_tva=Decimal("20"),
        total_catalogue_impose=500,
        payment_method=PaymentMethod.LOCAL_EURO,
    )
    ajouter_article(
        vente,
        pricesold=tarif_du_jus,
        quantite=Decimal("1.571429"),
        prix_unitaire=350,
        taux_tva=Decimal("20"),
        total_catalogue_impose=550,
        payment_method=PaymentMethod.CC,
    )
    ajouter_reglement(vente, moyen=PaymentMethod.LOCAL_EURO, montant=500)
    ajouter_reglement(vente, moyen=PaymentMethod.CC, montant=550)
    vente_reglee = encaisser_vente(vente)
    verifier_egalites(vente_reglee)
    return Vente.objects.get(pk=vente_reglee.pk)


def vendre_une_biere(client_de_la_vente, moyen, origine=SaleOrigin.LABOUTIK, point_de_vente=None):
    """
    Une vente réglée d'une bière à 5,00 €, au client et au moyen donnés. Rend la vente.
    / A settled sale of one 5.00 beer, given customer and method.
    """
    vente = ouvrir_vente(
        origine=origine,
        nature=Vente.Nature.VENTE,
        point_de_vente=point_de_vente,
        client=client_de_la_vente,
    )
    ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Biere", prix_en_euros="5.00"),
        quantite=Decimal("1"),
        prix_unitaire=500,
        taux_tva=Decimal("20"),
        payment_method=moyen,
    )
    ajouter_reglement(vente, moyen=moyen, montant=500)
    return Vente.objects.get(pk=encaisser_vente(vente).pk)


def ouvrir_une_vente_en_ligne_en_attente(client_de_la_vente, depuis_minutes):
    """
    Une vente en ligne restée « en attente » (un billet à 10,00 €, sans règlement),
    ouverte il y a `depuis_minutes` minutes : la date est posée par `update()`
    (tests/PIEGES.md 13.19). Rend la vente.
    / An online sale left pending, opened `depuis_minutes` ago. Returns it.
    """
    vente = ouvrir_vente(
        origine=SaleOrigin.LESPASS,
        nature=Vente.Nature.VENTE,
        client=client_de_la_vente,
    )
    ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Billet", prix_en_euros="10.00"),
        quantite=Decimal("1"),
        prix_unitaire=1000,
        taux_tva=Decimal("0"),
        payment_method=PaymentMethod.STRIPE_NOFED,
    )
    Vente.objects.filter(pk=vente.pk).update(
        datetime_creation=timezone.now() - timedelta(minutes=depuis_minutes)
    )
    return Vente.objects.get(pk=vente.pk)


def vendre_en_ligne_avec_un_ecart_d_encaissement(client_de_la_vente, ecart_en_centimes=100):
    """
    Une vente en ligne réglée où Stripe a encaissé un autre montant que le billet
    (10,00 €). Par défaut 1 € de plus : un article « Écart d'encaissement — reçu en
    plus » de 100, règlement Stripe 1100. Avec `ecart_en_centimes=-100` : « reçu en
    moins », règlement Stripe 900. Rend la vente.
    / An online sale where Stripe collected another amount (default 1.00 more): a gap
    item. Returns the sale.
    """
    vente = ouvrir_vente(
        origine=SaleOrigin.LESPASS,
        nature=Vente.Nature.VENTE,
        client=client_de_la_vente,
    )
    ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Billet", prix_en_euros="10.00"),
        quantite=Decimal("1"),
        prix_unitaire=1000,
        taux_tva=Decimal("0"),
        payment_method=PaymentMethod.STRIPE_NOFED,
    )
    ajouter_l_article_d_ecart_d_encaissement(vente, ecart_en_centimes)
    ajouter_reglement(
        vente, moyen=PaymentMethod.STRIPE_NOFED, montant=1000 + ecart_en_centimes
    )
    return Vente.objects.get(pk=encaisser_vente(vente).pk)


def ventes_de_la_liste(client_de_l_admin, **parametres):
    """
    Ouvre la liste des ventes avec ces paramètres (filtres, recherche). Rend la
    réponse et la liste des ventes de la page (`cl.result_list`).
    / Opens the sale list with these parameters: (response, sales of the page).
    """
    reponse = client_de_l_admin.get(ADRESSE_DE_LA_LISTE_DES_VENTES, parametres)
    assert reponse.status_code == 200, reponse.content.decode()[:400]
    return reponse, list(reponse.context["cl"].result_list)


def texte_de_la_page(reponse):
    """Le HTML de la page, les espaces insécables écrites en entité ramenées au
    caractère. / The page HTML, &nbsp; entities turned into the character."""
    return reponse.content.decode().replace("&nbsp;", chr(0xA0))


# --------------------------------------------------------------------------
# Le menu « Ventes & comptabilité »
# / The "Sales & accounting" menu
# --------------------------------------------------------------------------


def test_menu_ventes_en_premier_puis_rapport_puis_plan(lieu):
    """
    Le groupe « Ventes & comptabilité » de la barre latérale commence par « Ventes »
    (la liste des ventes), puis le rapport des ventes (les clôtures), puis le plan
    comptable.
    / The sidebar group starts with "Sales", then the sales report, then the chart of
    accounts.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    requete = client_de_l_admin.get("/admin/").wsgi_request
    navigation = get_sidebar_navigation(requete)

    adresse_des_clotures = "/admin/comptabilite/cloturecaisse/"
    liens_du_groupe = None
    for groupe in navigation:
        liens = []
        for item in groupe["items"]:
            liens.append(str(item.get("link") or ""))
        if adresse_des_clotures in liens:
            liens_du_groupe = liens
    assert liens_du_groupe is not None, "Le groupe « Ventes & comptabilité » est introuvable."

    assert liens_du_groupe[0] == ADRESSE_DE_LA_LISTE_DES_VENTES, liens_du_groupe
    rang_du_rapport = liens_du_groupe.index(adresse_des_clotures)
    # « Plan comptable » ouvre son onglet « Gérer », la balance.
    # / "Chart of accounts" opens its "Manage" tab, the trial balance.
    rang_du_plan = liens_du_groupe.index("/admin/laboutik/comptecomptable/balance/")
    assert 0 < rang_du_rapport < rang_du_plan, liens_du_groupe


# --------------------------------------------------------------------------
# La liste
# / The list
# --------------------------------------------------------------------------


def test_liste_des_ventes_colonnes(lieu):
    """
    Une vente de caisse réglée (fil rouge) au point de vente du test, pour un client
    au e-mail unique. Recherchée par cet e-mail, elle est la seule de la liste, et sa
    ligne montre : son numéro, son heure d'encaissement (heure du lieu), son origine
    (« Cash register », dans la langue de la page), son point de vente, l'e-mail du
    client, son total 10,50 €, la CB parmi ses moyens, sa nature et son statut.
    / The list row shows number, local time, origin, point of sale, customer e-mail,
    total 10.50, CB among the methods, nature and status.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    acheteur = creer_utilisateur()
    point_de_vente = creer_un_point_de_vente()
    vente = vendre_trois_jus_en_deux_parts(acheteur, point_de_vente=point_de_vente)

    reponse, ventes_affichees = ventes_de_la_liste(client_de_l_admin, q=acheteur.email)

    assert ventes_affichees == [vente]
    page = texte_de_la_page(reponse)
    fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
    heure_locale = vente.datetime_encaissement.astimezone(fuseau_du_lieu).strftime("%H:%M")
    langue_de_la_page = reponse.wsgi_request.LANGUAGE_CODE
    with translation.override(langue_de_la_page):
        libelle_de_l_origine = str(SaleOrigin.LABOUTIK.label)
        libelle_de_la_nature = str(Vente.Nature.VENTE.label)
        libelle_du_statut = str(Vente.Statut.REGLEE.label)
        libelle_de_la_cb = gettext("Carte bancaire")
    for texte_attendu in [
        str(vente.numero),
        heure_locale,
        libelle_de_l_origine,
        point_de_vente.name,
        acheteur.email,
        euros_a_la_francaise(1050),
        libelle_de_la_cb,
        libelle_de_la_nature,
        libelle_du_statut,
    ]:
        assert texte_attendu in page, texte_attendu


def test_liste_des_ventes_client_par_sa_carte(lieu):
    """
    Une vente sans client connu, faite avec une carte : la colonne « client » montre
    le numéro de la carte.
    / A sale without a known customer but with a card: the customer column shows the
    card number.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    numero_de_la_carte = identifiant_unique().upper()
    carte = CarteCashless.objects.create(
        tag_id=numero_de_la_carte, number=numero_de_la_carte
    )
    vente = vendre_trois_jus_en_deux_parts(None, carte=carte)

    reponse, ventes_affichees = ventes_de_la_liste(client_de_l_admin, q=numero_de_la_carte)

    assert ventes_affichees == [vente]
    assert numero_de_la_carte in texte_de_la_page(reponse)


def test_recherche_par_numero_de_vente(lieu):
    """
    La recherche par le numéro d'une vente la trouve.
    / Searching a sale number finds it.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_une_biere(creer_utilisateur(), PaymentMethod.CASH)

    _reponse, ventes_affichees = ventes_de_la_liste(client_de_l_admin, q=str(vente.numero))

    assert vente in ventes_affichees


@pytest.mark.parametrize(
    "parametre_du_filtre, valeur_qui_garde_la_vente_cb, valeur_qui_l_ecarte",
    [
        ("moyen", PaymentMethod.CC, PaymentMethod.CASH),
        ("origine__exact", SaleOrigin.LABOUTIK, SaleOrigin.LESPASS),
        ("nature__exact", Vente.Nature.VENTE, Vente.Nature.AVOIR),
        ("statut__exact", Vente.Statut.REGLEE, Vente.Statut.EN_ATTENTE),
    ],
)
def test_filtres_de_la_liste(
    lieu, parametre_du_filtre, valeur_qui_garde_la_vente_cb, valeur_qui_l_ecarte
):
    """
    Une bière réglée par CB à la caisse, une autre en espèces, pour le même client.
    Chaque filtre garde ou écarte la vente CB : moyen (une vente qui a un règlement de
    ce moyen), origine, nature, statut.
    / Each filter keeps or drops the CB sale: method (a payment of this method),
    origin, nature, status.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    acheteur = creer_utilisateur()
    vente_cb = vendre_une_biere(acheteur, PaymentMethod.CC)
    vendre_une_biere(acheteur, PaymentMethod.CASH)

    _reponse, ventes_gardees = ventes_de_la_liste(
        client_de_l_admin,
        q=acheteur.email,
        **{parametre_du_filtre: valeur_qui_garde_la_vente_cb},
    )
    _reponse, ventes_ecartees = ventes_de_la_liste(
        client_de_l_admin,
        q=acheteur.email,
        **{parametre_du_filtre: valeur_qui_l_ecarte},
    )

    assert vente_cb in ventes_gardees
    assert vente_cb not in ventes_ecartees


def test_filtre_par_point_de_vente(lieu):
    """
    Deux bières du même client, à deux points de vente : le filtre par point de vente
    ne garde que celle de ce point de vente.
    / The point of sale filter keeps the sale of that point of sale only.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    acheteur = creer_utilisateur()
    premier_point_de_vente = creer_un_point_de_vente()
    second_point_de_vente = creer_un_point_de_vente()
    vente_du_premier = vendre_une_biere(
        acheteur, PaymentMethod.CASH, point_de_vente=premier_point_de_vente
    )
    vendre_une_biere(acheteur, PaymentMethod.CASH, point_de_vente=second_point_de_vente)

    _reponse, ventes_affichees = ventes_de_la_liste(
        client_de_l_admin,
        q=acheteur.email,
        point_de_vente__uuid__exact=str(premier_point_de_vente.uuid),
    )

    assert ventes_affichees == [vente_du_premier]


def test_admin_filtre_ventes_a_verifier(lieu):
    """
    Fiche test 16. Le filtre « À vérifier » garde :
    - une vente en ligne en attente depuis 2 heures (encaissement en échec) ;
    - une vente réglée qui porte un article « Écart d'encaissement » (D26) ;
    et écarte :
    - une vente en ligne en attente depuis 10 minutes (le client paie peut-être) ;
    - une vente réglée ordinaire.
    / Sheet test 16: "To check" keeps a sale pending for 2 hours and a sale with a
    gap item; drops a sale pending for 10 minutes and an ordinary settled sale.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    acheteur = creer_utilisateur()
    vente_en_attente_depuis_deux_heures = ouvrir_une_vente_en_ligne_en_attente(
        acheteur, depuis_minutes=120
    )
    vente_avec_un_ecart = vendre_en_ligne_avec_un_ecart_d_encaissement(acheteur)
    vente_en_attente_depuis_dix_minutes = ouvrir_une_vente_en_ligne_en_attente(
        acheteur, depuis_minutes=10
    )
    vente_ordinaire = vendre_une_biere(acheteur, PaymentMethod.CASH)

    _reponse, ventes_a_verifier = ventes_de_la_liste(
        client_de_l_admin, q=acheteur.email, a_verifier="oui"
    )

    assert vente_en_attente_depuis_deux_heures in ventes_a_verifier
    assert vente_avec_un_ecart in ventes_a_verifier
    assert vente_en_attente_depuis_dix_minutes not in ventes_a_verifier
    assert vente_ordinaire not in ventes_a_verifier


def requetes_de_la_liste_des_ventes(client_de_l_admin, adresse_e_mail):
    """
    Ouvre la liste des ventes, recherchée par l'e-mail d'un client. Rend (nombre de
    requêtes, nombre de ventes affichées).
    / Opens the sale list searched by a customer e-mail: (queries, sales shown).
    """
    with CaptureQueriesContext(connection) as requetes:
        reponse = client_de_l_admin.get(
            ADRESSE_DE_LA_LISTE_DES_VENTES, {"q": adresse_e_mail}
        )
    assert reponse.status_code == 200
    return len(requetes), len(reponse.context["cl"].result_list)


def test_liste_des_ventes_nombre_de_requetes_constant(lieu):
    """
    La liste des ventes coûte le même nombre de requêtes pour 1 vente et pour 3
    (point de vente, client, carte, règlements préchargés).
    / The sale list costs the same number of queries for 1 and 3 sales.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    client_d_une_vente = creer_utilisateur()
    client_de_trois_ventes = creer_utilisateur()
    point_de_vente = creer_un_point_de_vente()
    vendre_trois_jus_en_deux_parts(client_d_une_vente, point_de_vente=point_de_vente)
    for _numero_de_la_vente in range(3):
        vendre_trois_jus_en_deux_parts(client_de_trois_ventes, point_de_vente=point_de_vente)
    # Un premier passage remplit les caches : il ne compte pas.
    # / A first pass fills the caches: it does not count.
    requetes_de_la_liste_des_ventes(client_de_l_admin, client_d_une_vente.email)

    requetes_pour_une, ventes_une = requetes_de_la_liste_des_ventes(
        client_de_l_admin, client_d_une_vente.email
    )
    requetes_pour_trois, ventes_trois = requetes_de_la_liste_des_ventes(
        client_de_l_admin, client_de_trois_ventes.email
    )

    assert ventes_une == 1
    assert ventes_trois == 3
    assert requetes_pour_trois == requetes_pour_une


# --------------------------------------------------------------------------
# La fiche
# / The detail page
# --------------------------------------------------------------------------


def test_admin_fiche_vente_articles_et_reglements(lieu):
    """
    Fiche test 14. La fiche d'une vente (fil rouge) montre ses articles (le produit,
    le prix unitaire 3,50 €, les totaux des parts 5,00 € et 5,50 €) et ses règlements
    (la CB, ses montants), et le badge « Intégrité OK ».
    / Sheet test 14: the detail page shows items, payments and "Integrity OK".
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_en_deux_parts(creer_utilisateur())
    nom_du_produit = vente.articles.first().pricesold.productsold.product.name

    reponse = client_de_l_admin.get(adresse_de_la_fiche(vente))

    assert reponse.status_code == 200
    page = texte_de_la_page(reponse)
    langue_de_la_page = reponse.wsgi_request.LANGUAGE_CODE
    with translation.override(langue_de_la_page):
        libelle_de_la_cb = gettext("Carte bancaire")
        texte_integrite_ok = gettext("Intégrité OK")
    for texte_attendu in [
        nom_du_produit,
        euros_a_la_francaise(350),
        euros_a_la_francaise(500),
        euros_a_la_francaise(550),
        libelle_de_la_cb,
    ]:
        assert texte_attendu in page, texte_attendu
    assert 'data-testid="vente-integrite"' in page
    assert texte_integrite_ok in page


def test_admin_fiche_vente_integrite_ko_si_la_vente_est_alteree(lieu):
    """
    Une vente réglée dont le total est modifié en base après coup (`update()`, sans
    passer par le service) : son empreinte recalculée ne correspond plus. La fiche
    montre « Intégrité KO », jamais « Intégrité OK ».
    / A settled sale altered in the database: the page shows "Integrity KO".
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_en_deux_parts(creer_utilisateur())
    Reglement.objects.filter(vente=vente, moyen=PaymentMethod.CC).update(montant=551)

    reponse = client_de_l_admin.get(adresse_de_la_fiche(vente))

    assert reponse.status_code == 200
    page = texte_de_la_page(reponse)
    langue_de_la_page = reponse.wsgi_request.LANGUAGE_CODE
    with translation.override(langue_de_la_page):
        texte_integrite_ok = gettext("Intégrité OK")
        texte_integrite_ko = gettext("Intégrité KO")
    assert texte_integrite_ko in page
    assert texte_integrite_ok not in page


def test_admin_fiche_vente_liens_vers_vente_liee_et_ventes_derivees(lieu):
    """
    Une vente en espèces, puis sa correction en CB (vente CORRECTION liée). La fiche
    de la vente porte un lien vers la correction (vente dérivée) ; la fiche de la
    correction porte un lien vers la vente d'origine (vente liée).
    / The sale page links to its correction; the correction page links back.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_une_biere(creer_utilisateur(), PaymentMethod.CASH)
    correction = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.CORRECTION,
        vente_liee=vente,
    )
    ajouter_reglement(correction, moyen=PaymentMethod.CASH, montant=-500)
    ajouter_reglement(correction, moyen=PaymentMethod.CC, montant=500)
    encaisser_vente(correction)

    reponse_de_la_vente = client_de_l_admin.get(adresse_de_la_fiche(vente))
    reponse_de_la_correction = client_de_l_admin.get(adresse_de_la_fiche(correction))

    assert reponse_de_la_vente.status_code == 200
    assert reponse_de_la_correction.status_code == 200
    assert adresse_de_la_fiche(correction) in reponse_de_la_vente.content.decode()
    assert adresse_de_la_fiche(vente) in reponse_de_la_correction.content.decode()


# --------------------------------------------------------------------------
# Lecture seule
# / Read-only
# --------------------------------------------------------------------------


def test_admin_vente_ajout_modification_suppression_refuses(lieu):
    """
    L'admin des ventes refuse l'ajout, la modification et la suppression, même à un
    administrateur du lieu ; la consultation est permise.
    / The sale admin refuses add, change and delete; viewing is allowed.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_une_biere(creer_utilisateur(), PaymentMethod.CASH)
    requete = RequestFactory().get(ADRESSE_DE_LA_LISTE_DES_VENTES)
    requete.user = client_de_l_admin.administrateur
    admin_des_ventes = staff_admin_site._registry[Vente]

    assert admin_des_ventes.has_view_permission(requete, vente) is True
    assert admin_des_ventes.has_add_permission(requete) is False
    assert admin_des_ventes.has_change_permission(requete, vente) is False
    assert admin_des_ventes.has_delete_permission(requete, vente) is False


def test_admin_vente_ecriture_refusee_par_les_adresses(lieu):
    """
    Par les adresses : la page d'ajout est refusée (403), et un envoi (POST) sur la
    fiche ne modifie rien (403, la vente garde son total).
    / Through the addresses: add page refused (403); a POST on the page changes
    nothing.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_une_biere(creer_utilisateur(), PaymentMethod.CASH)

    reponse_de_l_ajout = client_de_l_admin.get(ADRESSE_DE_L_AJOUT_D_UNE_VENTE)
    reponse_de_la_modification = client_de_l_admin.post(
        adresse_de_la_fiche(vente), {"total_ttc": "1"}
    )

    assert reponse_de_l_ajout.status_code == 403
    assert reponse_de_la_modification.status_code == 403
    vente.refresh_from_db()
    assert vente.total_ttc == 500


# --------------------------------------------------------------------------
# Action « Avoir total »
# / "Full credit note" action
# --------------------------------------------------------------------------


def adresse_de_l_avoir_total(vente):
    """L'adresse de l'action « Avoir total » d'une vente. / The action address."""
    return f"/admin/BaseBillet/vente/{vente.uuid}/avoir_total/"


def adresse_du_rejeu_de_l_encaissement(vente):
    """L'adresse de l'action « Rejouer l'encaissement ». / The action address."""
    return f"/admin/BaseBillet/vente/{vente.uuid}/rejouer_encaissement/"


def ventes_d_avoir_de(vente):
    """Les ventes AVOIR liées à cette vente. / The AVOIR sales linked to this sale."""
    return list(Vente.objects.filter(vente_liee=vente, nature=Vente.Nature.AVOIR))


def moyens_et_montants(vente):
    """Les règlements de la vente : (moyen, montant), triés. / Sorted payments."""
    reglements = []
    for reglement in Reglement.objects.filter(vente=vente):
        reglements.append((reglement.moyen, reglement.montant))
    return sorted(reglements)


def la_reponse_porte_un_message_d_erreur(reponse):
    """Dit si l'action a laissé au moins un message d'erreur à l'admin.
    / Tells whether the action left at least one error message."""
    for message in get_messages(reponse.wsgi_request):
        if message.level == messages.ERROR:
            return True
    return False


def vendre_trois_jus_par_cb(client_de_la_vente):
    """
    Une vente de caisse réglée : 3 jus à 3,50 € (une ligne, quantité 3), payés 10,50 €
    par CB. Rend la vente.
    / A settled register sale: 3 juices paid 10.50 by card. Returns the sale.
    """
    vente = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.VENTE,
        client=client_de_la_vente,
    )
    ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Jus", prix_en_euros="3.50"),
        quantite=Decimal("3"),
        prix_unitaire=350,
        taux_tva=Decimal("20"),
        payment_method=PaymentMethod.CC,
        status=LigneArticle.VALID,
    )
    ajouter_reglement(vente, moyen=PaymentMethod.CC, montant=1050)
    return Vente.objects.get(pk=encaisser_vente(vente).pk)


def test_admin_avoir_total_rembourse_par_especes(lieu):
    """
    Fiche test 15. Une vente de caisse payée 10,50 € par CB. L'admin ouvre « Avoir
    total » : l'écran a le champ « Remboursé par ». Il choisit « Espèces » et valide.
    Une vente AVOIR, liée à la vente, réglée : total −1050, UN seul règlement espèces
    −1050 ; ses deux égalités tiennent.
    / Sheet test 15: a 10.50 card sale, full credit note refunded in cash: one AVOIR
    sale of −1050 with one cash payment of −1050.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_par_cb(creer_utilisateur())

    reponse_de_l_ecran = client_de_l_admin.get(adresse_de_l_avoir_total(vente))
    assert reponse_de_l_ecran.status_code == 200
    assert "moyen_rembourse" in reponse_de_l_ecran.context["form"].fields

    reponse = client_de_l_admin.post(
        adresse_de_l_avoir_total(vente), {"moyen_rembourse": PaymentMethod.CASH}
    )

    assert reponse.status_code == 302
    avoirs = ventes_d_avoir_de(vente)
    assert len(avoirs) == 1
    vente_d_avoir = avoirs[0]
    assert vente_d_avoir.statut == Vente.Statut.REGLEE
    assert vente_d_avoir.total_ttc == -1050
    assert moyens_et_montants(vente_d_avoir) == [(PaymentMethod.CASH, -1050)]
    verifier_egalites(vente_d_avoir)


def test_admin_avoir_total_deux_moyens_un_seul_rembourse_par(lieu):
    """
    Q-G10. Une vente payée par deux moyens (fil rouge : 5,00 € monnaie locale + 5,50 €
    CB, deux parts). « Avoir total » remboursé par chèque : UNE vente AVOIR avec ses
    deux articles (−500 et −550), et UN seul règlement chèque −1050 pour tout l'argent.
    / Q-G10: a two-method sale; one credit note sale, two items, ONE cheque payment.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_en_deux_parts(creer_utilisateur())

    reponse = client_de_l_admin.post(
        adresse_de_l_avoir_total(vente), {"moyen_rembourse": PaymentMethod.CHEQUE}
    )

    assert reponse.status_code == 302
    avoirs = ventes_d_avoir_de(vente)
    assert len(avoirs) == 1
    vente_d_avoir = avoirs[0]
    nets_des_articles = []
    for article in vente_d_avoir.articles.all():
        nets_des_articles.append(article.total_ttc)
    assert sorted(nets_des_articles) == [-550, -500]
    assert moyens_et_montants(vente_d_avoir) == [(PaymentMethod.CHEQUE, -1050)]
    verifier_egalites(vente_d_avoir)


def test_admin_avoir_total_vente_entierement_offerte_sans_rembourse_par(lieu):
    """
    Une vente entièrement offerte (une bière à 5,00 €, offerte : règlement « offert »
    500). L'écran « Avoir total » n'a PAS de champ « Remboursé par » : il n'y a pas
    d'argent à rendre. L'avoir n'a qu'un règlement « offert » −500.
    / A fully offered sale: no "Refunded by" field; the credit note has one FREE
    payment of −500.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE)
    ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Biere offerte", prix_en_euros="5.00"),
        quantite=Decimal("1"),
        prix_unitaire=500,
        taux_tva=Decimal("20"),
        offert_en_totalite=True,
        status=LigneArticle.VALID,
    )
    vente = Vente.objects.get(pk=encaisser_vente(vente).pk)

    reponse_de_l_ecran = client_de_l_admin.get(adresse_de_l_avoir_total(vente))
    reponse = client_de_l_admin.post(adresse_de_l_avoir_total(vente), {})

    assert reponse_de_l_ecran.status_code == 200
    assert "moyen_rembourse" not in reponse_de_l_ecran.context["form"].fields
    assert reponse.status_code == 302
    avoirs = ventes_d_avoir_de(vente)
    assert len(avoirs) == 1
    assert moyens_et_montants(avoirs[0]) == [(PaymentMethod.FREE, -500)]


def test_admin_avoir_total_vente_payee_par_stripe_regle_d27(lieu):
    """
    D27. Une vente en ligne payée 10,00 € par Stripe. « Avoir total » : l'écran n'a PAS
    de champ « Remboursé par ». L'avoir a UN règlement négatif au moyen Stripe
    d'origine (« SN », −1000), relié au paiement, référence externe vide. Aucun appel
    à Stripe. Un message rappelle de rembourser depuis le tableau de bord Stripe.
    / D27: a Stripe-paid sale: no field, one negative payment at the original Stripe
    method, empty reference, no Stripe call, a reminder message.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente, paiement = ouvrir_une_vente_stripe_en_attente_paiement_valide()
    encaisser_vente_stripe(paiement)
    vente.refresh_from_db()

    with patch("stripe.Refund.create") as remboursement_stripe:
        reponse_de_l_ecran = client_de_l_admin.get(adresse_de_l_avoir_total(vente))
        reponse = client_de_l_admin.post(adresse_de_l_avoir_total(vente), {})

    assert reponse_de_l_ecran.status_code == 200
    assert "moyen_rembourse" not in reponse_de_l_ecran.context["form"].fields
    # Le rappel de l'écran dit la somme à rembourser depuis Stripe.
    # / The screen reminder states the amount to refund from Stripe.
    rappels_stripe = textes_des_elements(
        reponse_de_l_ecran.content.decode(), "avoir-rappel-stripe"
    )
    assert len(rappels_stripe) == 1
    assert texte_sans_espaces_en_trop(euros_a_la_francaise(1000)) in rappels_stripe[0]
    assert reponse.status_code == 302
    assert remboursement_stripe.call_count == 0
    avoirs = ventes_d_avoir_de(vente)
    assert len(avoirs) == 1
    assert moyens_et_montants(avoirs[0]) == [(PaymentMethod.STRIPE_NOFED, -1000)]
    reglement_de_l_avoir = Reglement.objects.get(vente=avoirs[0])
    assert reglement_de_l_avoir.reference_externe == ""
    assert reglement_de_l_avoir.paiement_stripe_id == paiement.pk
    textes_des_messages = []
    for message in get_messages(reponse.wsgi_request):
        textes_des_messages.append(str(message))
    with translation.override(reponse.wsgi_request.LANGUAGE_CODE):
        rappel_attendu = gettext("Remboursez cette somme depuis votre tableau de bord Stripe.")
    assert rappel_attendu in textes_des_messages
    verifier_egalites(avoirs[0])


def test_admin_avoir_total_vente_deja_remboursee_en_partie_rend_le_reste(lieu):
    """
    Une vente CB de deux articles : une bière à 5,00 € et un jus à 3,50 € (8,50 €).
    La bière a déjà son avoir (l'avoir d'une ligne, rendu en espèces). « Avoir total »
    rend TOUT CE QUI RESTE : une nouvelle vente AVOIR avec le seul jus (−350), et un
    règlement espèces −350.
    / A sale partly credited already: the full credit note gives back what is left
    (the juice only, −350).
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE, client=creer_utilisateur()
    )
    ligne_de_la_biere = ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Biere", prix_en_euros="5.00"),
        quantite=Decimal("1"),
        prix_unitaire=500,
        taux_tva=Decimal("20"),
        payment_method=PaymentMethod.CC,
        status=LigneArticle.VALID,
    )
    ligne_du_jus = ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Jus", prix_en_euros="3.50"),
        quantite=Decimal("1"),
        prix_unitaire=350,
        taux_tva=Decimal("20"),
        payment_method=PaymentMethod.CC,
        status=LigneArticle.VALID,
    )
    ajouter_reglement(vente, moyen=PaymentMethod.CC, montant=850)
    vente = Vente.objects.get(pk=encaisser_vente(vente).pk)
    ecrire_la_vente_d_avoir_d_une_ligne(
        LigneArticle.objects.get(pk=ligne_de_la_biere.pk),
        quantite=Decimal("1"),
        moyen_rembourse=PaymentMethod.CASH,
        origine=SaleOrigin.ADMIN,
    )

    reponse = client_de_l_admin.post(
        adresse_de_l_avoir_total(vente), {"moyen_rembourse": PaymentMethod.CASH}
    )

    assert reponse.status_code == 302
    avoirs = ventes_d_avoir_de(vente)
    assert len(avoirs) == 2
    avoir_total = Vente.objects.get(
        nature=Vente.Nature.AVOIR, vente_liee=vente, articles__credit_note_for=ligne_du_jus
    )
    lignes_rendues = []
    for article in avoir_total.articles.all():
        lignes_rendues.append((article.credit_note_for_id, article.total_ttc))
    assert lignes_rendues == [(ligne_du_jus.pk, -350)]
    assert moyens_et_montants(avoir_total) == [(PaymentMethod.CASH, -350)]
    verifier_egalites(avoir_total)


def test_avoir_total_les_articles_passent_credit_note(lieu):
    """
    Après un « Avoir total » (fil rouge, deux parts), chaque article de la vente AVOIR
    est au statut CREDIT_NOTE : la transition part APRÈS l'encaissement.
    / After a full credit note, every credit note item is CREDIT_NOTE.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_en_deux_parts(creer_utilisateur())

    client_de_l_admin.post(
        adresse_de_l_avoir_total(vente), {"moyen_rembourse": PaymentMethod.CASH}
    )

    vente_d_avoir = ventes_d_avoir_de(vente)[0]
    statuts_des_articles = []
    for article in vente_d_avoir.articles.all():
        statuts_des_articles.append(article.status)
    # Comparaison triée : l'ordre de lecture des articles n'est pas garanti.
    # / Sorted comparison: the read order of the items is not guaranteed.
    assert sorted(statuts_des_articles) == [LigneArticle.CREDIT_NOTE, LigneArticle.CREDIT_NOTE]


# Les gardes du SERVICE, testées sans l'écran : l'écran a ses propres gardes (tests
# plus haut), le service doit refuser seul, pour tout autre appelant.
# / The SERVICE guards, tested without the screen: the service must refuse on its own.


def test_service_avoir_d_une_vente_refuse_une_nature_autre_que_vente(lieu):
    """
    `ecrire_la_vente_d_avoir_d_une_vente` sur une vente AVOIR (l'avoir d'une vente
    CB) : ValueError, aucune vente de plus.
    / The service refuses a non-VENTE sale: ValueError, nothing written.
    """
    vente = vendre_trois_jus_par_cb(creer_utilisateur())
    vente_d_avoir = ecrire_la_vente_d_avoir_d_une_vente(
        vente, moyen_rembourse=PaymentMethod.CASH, origine=SaleOrigin.ADMIN
    )
    nombre_de_ventes_avant = Vente.objects.count()

    with pytest.raises(ValueError):
        ecrire_la_vente_d_avoir_d_une_vente(
            vente_d_avoir, moyen_rembourse=PaymentMethod.CASH, origine=SaleOrigin.ADMIN
        )

    assert Vente.objects.count() == nombre_de_ventes_avant


def test_service_avoir_d_une_vente_refuse_une_vente_pas_reglee(lieu):
    """
    `ecrire_la_vente_d_avoir_d_une_vente` sur une vente encore en attente : ValueError,
    aucun avoir.
    / The service refuses an unsettled sale: ValueError, no credit note.
    """
    vente = ouvrir_une_vente_en_ligne_en_attente(creer_utilisateur(), depuis_minutes=120)

    with pytest.raises(ValueError):
        ecrire_la_vente_d_avoir_d_une_vente(
            vente, moyen_rembourse=PaymentMethod.CASH, origine=SaleOrigin.ADMIN
        )

    assert ventes_d_avoir_de(vente) == []


def test_service_avoir_d_une_vente_refuse_quand_rien_ne_reste(lieu):
    """
    `ecrire_la_vente_d_avoir_d_une_vente` appelé deux fois sur la même vente CB : le
    second appel lève ValueError (rien ne reste à rendre), un seul avoir.
    / Called twice: the second call raises ValueError (nothing left), one credit note.
    """
    vente = vendre_trois_jus_par_cb(creer_utilisateur())
    ecrire_la_vente_d_avoir_d_une_vente(
        vente, moyen_rembourse=PaymentMethod.CASH, origine=SaleOrigin.ADMIN
    )

    with pytest.raises(ValueError):
        ecrire_la_vente_d_avoir_d_une_vente(
            vente, moyen_rembourse=PaymentMethod.CASH, origine=SaleOrigin.ADMIN
        )

    assert len(ventes_d_avoir_de(vente)) == 1


def test_admin_avoir_total_sans_rembourse_par_refuse(lieu):
    """
    Une vente payée en CB : l'admin valide « Avoir total » sans choisir « Remboursé
    par ». L'écran revient (200), aucun avoir n'est écrit.
    / Confirming without "Refunded by": the screen comes back, nothing written.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_par_cb(creer_utilisateur())

    reponse = client_de_l_admin.post(adresse_de_l_avoir_total(vente), {})

    assert reponse.status_code == 200
    assert ventes_d_avoir_de(vente) == []


def test_admin_avoir_total_refuse_vente_pas_reglee(lieu):
    """
    Une vente encore « en attente » (encaissement en ligne en échec) : « Avoir total »
    est refusé, avec un message d'erreur ; aucun avoir.
    / An unsettled sale: refused with an error message, no credit note.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = ouvrir_une_vente_en_ligne_en_attente(creer_utilisateur(), depuis_minutes=120)

    reponse = client_de_l_admin.post(
        adresse_de_l_avoir_total(vente), {"moyen_rembourse": PaymentMethod.CASH}
    )

    assert reponse.status_code == 302
    assert la_reponse_porte_un_message_d_erreur(reponse)
    assert ventes_d_avoir_de(vente) == []


def test_admin_avoir_total_refuse_vente_deja_remboursee_en_totalite(lieu):
    """
    Une vente CB : un premier « Avoir total » passe. Le second est refusé, avec un
    message d'erreur : la vente est déjà remboursée en totalité. Un seul avoir.
    / A second full credit note on the same sale is refused: one credit note only.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_par_cb(creer_utilisateur())
    client_de_l_admin.post(
        adresse_de_l_avoir_total(vente), {"moyen_rembourse": PaymentMethod.CASH}
    )

    seconde_reponse = client_de_l_admin.post(
        adresse_de_l_avoir_total(vente), {"moyen_rembourse": PaymentMethod.CASH}
    )

    assert seconde_reponse.status_code == 302
    assert la_reponse_porte_un_message_d_erreur(seconde_reponse)
    assert len(ventes_d_avoir_de(vente)) == 1


@pytest.mark.parametrize("nature_refusee", [Vente.Nature.AVOIR, Vente.Nature.CORRECTION])
def test_admin_avoir_total_refuse_une_nature_autre_que_vente(lieu, nature_refusee):
    """
    « Avoir total » n'existe que pour une vente de nature VENTE. Sur un avoir (l'avoir
    d'une vente CB) ou sur une correction de moyen, il est refusé avec un message
    d'erreur ; aucun avoir de plus n'est écrit.
    / Refused on a credit note or a correction: error message, nothing written.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_par_cb(creer_utilisateur())
    if nature_refusee == Vente.Nature.AVOIR:
        client_de_l_admin.post(
            adresse_de_l_avoir_total(vente), {"moyen_rembourse": PaymentMethod.CASH}
        )
        vente_refusee = ventes_d_avoir_de(vente)[0]
    else:
        vente_refusee = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.CORRECTION,
            vente_liee=vente,
        )
        ajouter_reglement(vente_refusee, moyen=PaymentMethod.CC, montant=-1050)
        ajouter_reglement(vente_refusee, moyen=PaymentMethod.CASH, montant=1050)
        vente_refusee = Vente.objects.get(pk=encaisser_vente(vente_refusee).pk)
    nombre_de_ventes_avant = Vente.objects.count()

    reponse = client_de_l_admin.post(
        adresse_de_l_avoir_total(vente_refusee), {"moyen_rembourse": PaymentMethod.CASH}
    )

    assert reponse.status_code == 302
    assert la_reponse_porte_un_message_d_erreur(reponse)
    assert Vente.objects.count() == nombre_de_ventes_avant


# --------------------------------------------------------------------------
# Action « Rejouer l'encaissement »
# / "Replay settlement" action
# --------------------------------------------------------------------------


def ouvrir_une_vente_stripe_en_attente_paiement_valide(categorie_article=Product.NONE):
    """
    L'état réel après un encaissement en ligne en échec : la vente est « en attente »,
    sans règlement, et son paiement Stripe est déjà VALID (passé par son propre
    `pre_save`, avec le montant encaissé 1000 et le moyen « SN »). Un billet à
    10,00 €, ligne validée, reliée au paiement. `categorie_article` : la catégorie du
    produit (BILLET pour une ligne qui part à l'ancien LaBoutik). Rend (vente, paiement).
    / The real state after a failed online settlement: pending sale, VALID payment.
    """
    acheteur = creer_utilisateur()
    vente = ouvrir_vente(
        origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur
    )
    # Une création : aucune transition de la machine à états ne part.
    # / A creation: no state machine transition runs.
    paiement = Paiement_stripe.objects.create(
        user=acheteur,
        status=Paiement_stripe.VALID,
        moyen=PaymentMethod.STRIPE_NOFED,
        montant_encaisse=1000,
        payment_intent_id=f"pi_test_{identifiant_unique()}",
        vente=vente,
    )
    ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(
            nom="Billet", prix_en_euros="10.00", categorie_article=categorie_article
        ),
        quantite=Decimal("1"),
        prix_unitaire=1000,
        taux_tva=Decimal("0"),
        payment_method=PaymentMethod.STRIPE_NOFED,
        paiement_stripe=paiement,
        status=LigneArticle.VALID,
    )
    return Vente.objects.get(pk=vente.pk), paiement


def test_admin_rejouer_l_encaissement(lieu):
    """
    Fiche test 16b. Une vente Stripe « en attente », paiement déjà VALID (l'état réel
    après un encaissement en échec). L'admin lance « Rejouer l'encaissement » : la
    vente passe RÉGLÉE, avec UN règlement « SN » de 1000 relié au paiement. Le
    paiement n'est JAMAIS réenregistré (`save()`) : VALID → VALID ne rejouerait rien.
    / Sheet test 16b: replaying settles the sale with one payment; the Stripe payment
    is never saved again.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente, paiement = ouvrir_une_vente_stripe_en_attente_paiement_valide()

    with patch.object(
        Paiement_stripe, "save", autospec=True, side_effect=Paiement_stripe.save
    ) as enregistrement_du_paiement:
        reponse = client_de_l_admin.post(adresse_du_rejeu_de_l_encaissement(vente))

    assert reponse.status_code == 302
    vente.refresh_from_db()
    assert vente.statut == Vente.Statut.REGLEE
    assert moyens_et_montants(vente) == [(PaymentMethod.STRIPE_NOFED, 1000)]
    assert Reglement.objects.get(vente=vente).paiement_stripe_id == paiement.pk
    assert enregistrement_du_paiement.call_count == 0
    verifier_egalites(vente)


def test_admin_rejouer_l_encaissement_refuse_vente_deja_reglee(lieu):
    """
    Une vente déjà réglée : « Rejouer l'encaissement » est refusé, avec un message
    d'erreur ; ses règlements ne changent pas.
    / Already settled: refused with an error message, payments unchanged.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_par_cb(creer_utilisateur())

    reponse = client_de_l_admin.post(adresse_du_rejeu_de_l_encaissement(vente))

    assert reponse.status_code == 302
    assert la_reponse_porte_un_message_d_erreur(reponse)
    assert moyens_et_montants(vente) == [(PaymentMethod.CC, 1050)]


def test_admin_rejouer_l_encaissement_refuse_vente_sans_paiement_stripe(lieu):
    """
    Une vente « en attente » qui n'a pas de paiement Stripe : « Rejouer
    l'encaissement » est refusé, avec un message d'erreur ; elle reste en attente.
    / A pending sale without a Stripe payment: refused, stays pending.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = ouvrir_vente(origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE)

    reponse = client_de_l_admin.post(adresse_du_rejeu_de_l_encaissement(vente))

    assert reponse.status_code == 302
    assert la_reponse_porte_un_message_d_erreur(reponse)
    vente.refresh_from_db()
    assert vente.statut == Vente.Statut.EN_ATTENTE


# --------------------------------------------------------------------------
# Lien vers Stripe
# / Link to Stripe
# --------------------------------------------------------------------------


def test_admin_fiche_vente_lien_vers_le_remboursement_stripe(lieu):
    """
    Un billet payé par Stripe, puis remboursé par Stripe : la vente AVOIR a un
    règlement dont la référence externe est l'identifiant du remboursement (`re_…`).
    Sa fiche porte un lien vers le tableau de bord Stripe, avec cette référence dans
    l'adresse.
    / A Stripe refund: the credit note page links to the Stripe dashboard with the
    refund id.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(creer_utilisateur(), concert, quantite=1)
    with patch("stripe.Refund.create", side_effect=rembourser_comme_stripe):
        achat.reservation.cancel_and_refund_ticket(achat.reservation.tickets.get())
    reglement_du_remboursement = Reglement.objects.get(
        paiement_stripe=achat.paiement, montant__lt=0
    )
    reference_du_remboursement = reglement_du_remboursement.reference_externe
    assert reference_du_remboursement.startswith("re_")

    reponse = client_de_l_admin.get(adresse_de_la_fiche(reglement_du_remboursement.vente))

    assert reponse.status_code == 200
    lecteur_des_liens = LecteurDesLiens()
    lecteur_des_liens.feed(reponse.content.decode())
    liens_vers_stripe = []
    for lien in lecteur_des_liens.liens:
        adresse = lien["href"]
        if "dashboard.stripe.com" in adresse and reference_du_remboursement in adresse:
            liens_vers_stripe.append(adresse)
    assert len(liens_vers_stripe) >= 1


# --------------------------------------------------------------------------
# Corrections de la relecture (G-3-bis)
# / Review corrections (G-3-bis)
# --------------------------------------------------------------------------


def textes_des_messages(reponse):
    """Les textes des messages laissés à l'admin par la requête.
    / The texts of the messages left to the admin by the request."""
    textes = []
    for message in get_messages(reponse.wsgi_request):
        textes.append(str(message))
    return textes


def message_traduit(reponse, texte_source):
    """Le texte source, dans la langue de la réponse. / The source text, translated."""
    with translation.override(reponse.wsgi_request.LANGUAGE_CODE):
        return gettext(texte_source)


TEXTE_DU_REFUS_POUR_UN_ECART = (
    "Cette vente a un écart d'encaissement : aucun avoir n'est possible."
)
TEXTE_DU_REFUS_POUR_UNE_RECHARGE = (
    "Cette vente contient une recharge de carte : l'avoir total n'est pas possible."
)


@pytest.mark.parametrize(
    "ecart_en_centimes", [100, -100], ids=["recu_en_plus", "recu_en_moins"]
)
def test_avoir_total_refuse_une_vente_avec_un_ecart_d_encaissement(lieu, ecart_en_centimes):
    """
    Une vente en ligne qui porte un écart d'encaissement (reçu en plus, puis reçu en
    moins) : l'avoir total est refusé.
    - par le SERVICE : ValueError qui cite l'écart ;
    - par l'ADMIN : l'écran ne s'ouvre pas (GET → retour à la fiche) et la validation
      est refusée (POST), avec le message « aucun avoir n'est possible » (Q-H13).
    Aucun avoir n'est écrit.
    / A sale with a collection gap: the full credit note is refused by the service and
    by the admin (no screen, error message). Nothing written.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_en_ligne_avec_un_ecart_d_encaissement(
        creer_utilisateur(), ecart_en_centimes=ecart_en_centimes
    )

    with pytest.raises(ValueError, match="écart d'encaissement"):
        ecrire_la_vente_d_avoir_d_une_vente(
            vente, moyen_rembourse=PaymentMethod.CASH, origine=SaleOrigin.ADMIN
        )
    reponse_de_l_ecran = client_de_l_admin.get(adresse_de_l_avoir_total(vente))
    reponse_de_la_validation = client_de_l_admin.post(
        adresse_de_l_avoir_total(vente), {"moyen_rembourse": PaymentMethod.CASH}
    )

    assert reponse_de_l_ecran.status_code == 302
    assert message_traduit(reponse_de_l_ecran, TEXTE_DU_REFUS_POUR_UN_ECART) in (
        textes_des_messages(reponse_de_l_ecran)
    )
    assert reponse_de_la_validation.status_code == 302
    assert message_traduit(reponse_de_la_validation, TEXTE_DU_REFUS_POUR_UN_ECART) in (
        textes_des_messages(reponse_de_la_validation)
    )
    assert ventes_d_avoir_de(vente) == []


def vendre_une_recharge_de_carte_par_cb(client_de_la_vente):
    """
    Une vente de caisse réglée : une recharge de carte de 10,00 € (hors chiffre
    d'affaires), payée par CB. Rend la vente.
    / A settled register sale: a 10.00 card top-up paid by card. Returns the sale.
    """
    vente = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.VENTE,
        client=client_de_la_vente,
    )
    ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(
            nom="Recharge",
            prix_en_euros="10.00",
            taux_tva="0.00",
            categorie_article=Product.RECHARGE_CASHLESS,
        ),
        quantite=Decimal("1"),
        prix_unitaire=1000,
        taux_tva=Decimal("0"),
        payment_method=PaymentMethod.CC,
        status=LigneArticle.VALID,
    )
    ajouter_reglement(vente, moyen=PaymentMethod.CC, montant=1000)
    return Vente.objects.get(pk=encaisser_vente(vente).pk)


def test_avoir_total_refuse_une_vente_avec_une_recharge(lieu):
    """
    Une vente qui contient une recharge de carte (10,00 € par CB) : l'avoir total est
    refusé par le SERVICE (ValueError qui cite la recharge) et par l'ADMIN (GET et
    POST : retour à la fiche, message d'erreur). Aucun avoir n'est écrit.
    / A sale with a card top-up: refused by the service and by the admin.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_une_recharge_de_carte_par_cb(creer_utilisateur())

    with pytest.raises(ValueError, match="recharge de carte"):
        ecrire_la_vente_d_avoir_d_une_vente(
            vente, moyen_rembourse=PaymentMethod.CASH, origine=SaleOrigin.ADMIN
        )
    reponse_de_l_ecran = client_de_l_admin.get(adresse_de_l_avoir_total(vente))
    reponse_de_la_validation = client_de_l_admin.post(
        adresse_de_l_avoir_total(vente), {"moyen_rembourse": PaymentMethod.CASH}
    )

    assert reponse_de_l_ecran.status_code == 302
    assert message_traduit(reponse_de_l_ecran, TEXTE_DU_REFUS_POUR_UNE_RECHARGE) in (
        textes_des_messages(reponse_de_l_ecran)
    )
    assert reponse_de_la_validation.status_code == 302
    assert message_traduit(
        reponse_de_la_validation, TEXTE_DU_REFUS_POUR_UNE_RECHARGE
    ) in textes_des_messages(reponse_de_la_validation)
    assert ventes_d_avoir_de(vente) == []


TEXTE_DU_REFUS_POUR_UNE_VENTE_PAS_EN_EUROS = (
    "Cette vente n'est pas en euros (points ou temps) : l'avoir total n'est pas "
    "possible."
)


def vendre_une_planche_en_points(client_de_la_vente):
    """
    Une vente de caisse réglée EN POINTS : la vente est tenue dans la monnaie de points
    (`unite` = son uuid), une planche à 300 centièmes de points, TVA 0, moyen « points
    ou temps » (NM), un règlement NM de 300. Rend la vente.
    / A settled register sale in points (unit = the points currency). Returns it.
    """
    monnaie_de_points = uuid.uuid4()
    vente = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.VENTE,
        client=client_de_la_vente,
        unite=str(monnaie_de_points),
    )
    ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Planche en points", taux_tva="0.00"),
        quantite=Decimal("1"),
        prix_unitaire=300,
        taux_tva=Decimal("0"),
        payment_method=PaymentMethod.NON_MONETAIRE,
        asset=monnaie_de_points,
        status=LigneArticle.VALID,
    )
    ajouter_reglement(
        vente, moyen=PaymentMethod.NON_MONETAIRE, montant=300, asset=monnaie_de_points
    )
    return Vente.objects.get(pk=encaisser_vente(vente).pk)


def test_avoir_total_refuse_une_vente_en_points(lieu):
    """
    Une vente tenue en points : l'avoir total est refusé par le SERVICE (ValueError,
    message « pas en euros ») et par l'ADMIN (GET et POST : retour à la fiche, même
    message). Aucun avoir n'est écrit.
    / A points sale: refused by the service and by the admin, nothing written.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_une_planche_en_points(creer_utilisateur())

    with pytest.raises(ValueError, match="pas en euros"):
        ecrire_la_vente_d_avoir_d_une_vente(
            vente, moyen_rembourse=None, origine=SaleOrigin.ADMIN
        )
    reponse_de_l_ecran = client_de_l_admin.get(adresse_de_l_avoir_total(vente))
    reponse_de_la_validation = client_de_l_admin.post(adresse_de_l_avoir_total(vente), {})

    assert reponse_de_l_ecran.status_code == 302
    assert message_traduit(
        reponse_de_l_ecran, TEXTE_DU_REFUS_POUR_UNE_VENTE_PAS_EN_EUROS
    ) in textes_des_messages(reponse_de_l_ecran)
    assert reponse_de_la_validation.status_code == 302
    assert message_traduit(
        reponse_de_la_validation, TEXTE_DU_REFUS_POUR_UNE_VENTE_PAS_EN_EUROS
    ) in textes_des_messages(reponse_de_la_validation)
    assert ventes_d_avoir_de(vente) == []


def test_filtre_a_verifier_ecarte_le_panier_abandonne(lieu):
    """
    Deux ventes en ligne en attente depuis 2 heures :
    - l'une a un paiement Stripe EXPIRÉ (session abandonnée, rien de payé) : elle
      n'est PAS à vérifier ;
    - l'autre a un paiement Stripe PAYÉ (encaissement en échec) : elle est à vérifier.
    / Two sales pending for 2 hours: an expired Stripe session is not "to check"; a
    paid one is.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    acheteur = creer_utilisateur()
    vente_du_panier_abandonne = ouvrir_une_vente_en_ligne_en_attente(
        acheteur, depuis_minutes=120
    )
    Paiement_stripe.objects.create(
        user=acheteur, status=Paiement_stripe.EXPIRE, vente=vente_du_panier_abandonne
    )
    vente_payee_pas_encaissee = ouvrir_une_vente_en_ligne_en_attente(
        acheteur, depuis_minutes=120
    )
    Paiement_stripe.objects.create(
        user=acheteur, status=Paiement_stripe.PAID, vente=vente_payee_pas_encaissee
    )

    _reponse, ventes_a_verifier = ventes_de_la_liste(
        client_de_l_admin, q=acheteur.email, a_verifier="oui"
    )

    assert vente_du_panier_abandonne not in ventes_a_verifier
    assert vente_payee_pas_encaissee in ventes_a_verifier


def test_admin_rejouer_l_encaissement_renvoie_le_billet_a_l_ancien_laboutik(
    lieu, django_capture_on_commit_callbacks
):
    """
    Une vente Stripe en attente dont la ligne est un BILLET (paiement déjà VALID). Après
    un rejeu réussi, la ligne part à l'ancien LaBoutik, comme après un encaissement
    normal : `send_sale_to_laboutik.delay(pk de la ligne)`, après la validation en base.
    / After a successful replay, the ticket line is sent to legacy LaBoutik after the
    commit.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente, _paiement = ouvrir_une_vente_stripe_en_attente_paiement_valide(
        categorie_article=Product.BILLET
    )
    ligne_du_billet = LigneArticle.objects.get(vente=vente)

    with patch("BaseBillet.tasks.send_sale_to_laboutik.delay") as envoi_a_l_ancien_laboutik:
        with django_capture_on_commit_callbacks(execute=True):
            reponse = client_de_l_admin.post(adresse_du_rejeu_de_l_encaissement(vente))

    assert reponse.status_code == 302
    vente.refresh_from_db()
    assert vente.statut == Vente.Statut.REGLEE
    envoi_a_l_ancien_laboutik.assert_called_once_with(ligne_du_billet.pk)


def test_admin_avoir_total_ecran_annonce_le_reste_a_rendre(lieu):
    """
    Une vente CB : une bière à 5,00 € et un jus à 3,50 €. La bière a déjà son avoir.
    L'écran « Avoir total » (GET) annonce ce qui sera rendu au moyen choisi : 3,50 €
    (le reste), pas 8,50 €. Son titre dit le numéro de la vente.
    / After a partial refund, the screen announces the remaining 3.50 and its title
    names the sale number.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK, nature=Vente.Nature.VENTE, client=creer_utilisateur()
    )
    ligne_de_la_biere = ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Biere", prix_en_euros="5.00"),
        quantite=Decimal("1"),
        prix_unitaire=500,
        taux_tva=Decimal("20"),
        payment_method=PaymentMethod.CC,
        status=LigneArticle.VALID,
    )
    ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Jus", prix_en_euros="3.50"),
        quantite=Decimal("1"),
        prix_unitaire=350,
        taux_tva=Decimal("20"),
        payment_method=PaymentMethod.CC,
        status=LigneArticle.VALID,
    )
    ajouter_reglement(vente, moyen=PaymentMethod.CC, montant=850)
    vente = Vente.objects.get(pk=encaisser_vente(vente).pk)
    ecrire_la_vente_d_avoir_d_une_ligne(
        LigneArticle.objects.get(pk=ligne_de_la_biere.pk),
        quantite=Decimal("1"),
        moyen_rembourse=PaymentMethod.CASH,
        origine=SaleOrigin.ADMIN,
    )

    reponse = client_de_l_admin.get(adresse_de_l_avoir_total(vente))

    assert reponse.status_code == 200
    page = reponse.content.decode()
    sommes_au_moyen_choisi = textes_des_elements(page, "avoir-somme-rembourse-par")
    assert len(sommes_au_moyen_choisi) == 1
    assert texte_sans_espaces_en_trop(euros_a_la_francaise(350)) in sommes_au_moyen_choisi[0]
    titre_attendu = message_traduit(
        reponse, "Avoir total de la vente n° %(numero)s"
    ) % {"numero": vente.numero}
    assert reponse.context["title"] == titre_attendu
    assert titre_attendu in page


def test_liste_des_ventes_total_d_une_vente_en_attente(lieu):
    """
    Une vente en ligne en attente (un billet à 20,00 €, pas encore réglée : son total
    stocké n'est pas encore posé). La liste montre la somme de ses articles : 20,00 €.
    / A pending sale (a 20.00 ticket): the list shows the sum of its items.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    acheteur = creer_utilisateur()
    vente = ouvrir_vente(
        origine=SaleOrigin.LESPASS, nature=Vente.Nature.VENTE, client=acheteur
    )
    ajouter_article(
        vente,
        pricesold=creer_tarif_vendu(nom="Billet", prix_en_euros="20.00"),
        quantite=Decimal("1"),
        prix_unitaire=2000,
        taux_tva=Decimal("0"),
        payment_method=PaymentMethod.STRIPE_NOFED,
    )

    reponse, ventes_affichees = ventes_de_la_liste(client_de_l_admin, q=acheteur.email)

    assert ventes_affichees == [Vente.objects.get(pk=vente.pk)]
    assert euros_a_la_francaise(2000) in texte_de_la_page(reponse)


def test_admin_rejouer_l_encaissement_refuse_un_paiement_pas_paye(lieu):
    """
    Une vente en attente dont le seul paiement Stripe est EN ATTENTE (pas payé) :
    « Rejouer l'encaissement » est refusé, avec le message « pas payé » ; la vente
    reste en attente.
    / A pending sale whose only Stripe payment is not paid: refused, stays pending.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    acheteur = creer_utilisateur()
    vente = ouvrir_une_vente_en_ligne_en_attente(acheteur, depuis_minutes=120)
    Paiement_stripe.objects.create(
        user=acheteur, status=Paiement_stripe.PENDING, vente=vente
    )

    reponse = client_de_l_admin.post(adresse_du_rejeu_de_l_encaissement(vente))

    assert reponse.status_code == 302
    message_attendu = message_traduit(
        reponse, "Le paiement Stripe de cette vente n'est pas payé : rien à rejouer."
    )
    assert message_attendu in textes_des_messages(reponse)
    vente.refresh_from_db()
    assert vente.statut == Vente.Statut.EN_ATTENTE


def test_admin_rejouer_l_encaissement_prend_le_paiement_paye_meme_s_il_est_ancien(lieu):
    """
    Une vente en attente avec un paiement VALID, puis une session Stripe plus récente
    EXPIRÉE. Le rejeu prend le paiement PAYÉ (les paiements pas payés sont écartés
    avant de prendre le plus récent) : la vente passe RÉGLÉE, son règlement est relié
    au paiement payé.
    / A paid payment then a newer expired session: the replay uses the paid one.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente, paiement_paye = ouvrir_une_vente_stripe_en_attente_paiement_valide()
    session_expiree = Paiement_stripe.objects.create(
        user=paiement_paye.user, status=Paiement_stripe.EXPIRE, vente=vente
    )
    # La session expirée est la plus récente (date posée par `update()`).
    # / The expired session is the most recent one.
    Paiement_stripe.objects.filter(pk=session_expiree.pk).update(
        order_date=paiement_paye.order_date + timedelta(minutes=5)
    )

    reponse = client_de_l_admin.post(adresse_du_rejeu_de_l_encaissement(vente))

    assert reponse.status_code == 302
    vente.refresh_from_db()
    assert vente.statut == Vente.Statut.REGLEE
    assert Reglement.objects.get(vente=vente).paiement_stripe_id == paiement_paye.pk


def adresses_des_liens_de_la_fiche(client_de_l_admin, vente):
    """Les adresses des liens de la fiche d'une vente. / The detail page links."""
    reponse = client_de_l_admin.get(adresse_de_la_fiche(vente))
    assert reponse.status_code == 200
    lecteur_des_liens = LecteurDesLiens()
    lecteur_des_liens.feed(reponse.content.decode())
    adresses = []
    for lien in lecteur_des_liens.liens:
        adresses.append(lien["href"])
    return adresses


def la_fiche_a_le_bouton(adresses_des_liens, chemin_de_l_action):
    """Dit si un lien de la fiche mène à cette action. / Whether a link leads there."""
    for adresse in adresses_des_liens:
        if f"/{chemin_de_l_action}/" in adresse:
            return True
    return False


def test_fiche_vente_montre_seulement_les_actions_qui_ont_un_sens(lieu):
    """
    Les boutons de la fiche :
    - une vente CB réglée : « Avoir total » oui, « Rejouer l'encaissement » non ;
    - son avoir (nature AVOIR) : ni l'un ni l'autre ;
    - une vente Stripe en attente, paiement VALID : « Rejouer » oui, « Avoir total » non.
    / Detail buttons appear only when the action makes sense.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente_reglee = vendre_trois_jus_par_cb(creer_utilisateur())
    vente_d_avoir = ecrire_la_vente_d_avoir_d_une_vente(
        vendre_trois_jus_par_cb(creer_utilisateur()),
        moyen_rembourse=PaymentMethod.CASH,
        origine=SaleOrigin.ADMIN,
    )
    vente_en_attente, _paiement = ouvrir_une_vente_stripe_en_attente_paiement_valide()

    liens_de_la_vente_reglee = adresses_des_liens_de_la_fiche(client_de_l_admin, vente_reglee)
    liens_de_l_avoir = adresses_des_liens_de_la_fiche(client_de_l_admin, vente_d_avoir)
    liens_de_la_vente_en_attente = adresses_des_liens_de_la_fiche(
        client_de_l_admin, vente_en_attente
    )

    assert la_fiche_a_le_bouton(liens_de_la_vente_reglee, "avoir_total")
    assert not la_fiche_a_le_bouton(liens_de_la_vente_reglee, "rejouer_encaissement")
    assert not la_fiche_a_le_bouton(liens_de_l_avoir, "avoir_total")
    assert not la_fiche_a_le_bouton(liens_de_l_avoir, "rejouer_encaissement")
    assert la_fiche_a_le_bouton(liens_de_la_vente_en_attente, "rejouer_encaissement")
    assert not la_fiche_a_le_bouton(liens_de_la_vente_en_attente, "avoir_total")


def test_admin_avoir_total_pre_remplit_le_seul_moyen_de_la_vente(lieu):
    """
    Une vente payée par CB seule : l'écran « Avoir total » propose « Carte bancaire »
    d'avance dans « Remboursé par ».
    / A card-only sale: "Refunded by" is pre-filled with the card.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_par_cb(creer_utilisateur())

    reponse = client_de_l_admin.get(adresse_de_l_avoir_total(vente))

    assert reponse.status_code == 200
    assert reponse.context["form"].initial.get("moyen_rembourse") == PaymentMethod.CC


def test_fiche_vente_badge_sans_cle_d_integrite(lieu):
    """
    Un lieu sans clé d'intégrité : le badge de la fiche d'une vente réglée dit « Pas de
    clé d'intégrité pour ce lieu » (pas « Intégrité KO »).
    / A venue without an integrity key: the badge says so, not "KO".
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_par_cb(creer_utilisateur())

    with patch.object(LaboutikConfiguration, "get_hmac_key", return_value=None):
        reponse = client_de_l_admin.get(adresse_de_la_fiche(vente))

    assert reponse.status_code == 200
    badges = textes_des_elements(reponse.content.decode(), "vente-integrite")
    assert badges == [message_traduit(reponse, "Pas de clé d'intégrité pour ce lieu")]


def test_admin_avoir_total_erreur_de_la_base_message_pas_de_500(lieu):
    """
    L'écriture de l'avoir échoue sur une erreur de la base (verrou) : l'admin reçoit un
    message d'erreur et revient à la fiche (302), pas une page 500. Aucun avoir.
    / A database error while writing: an error message, no 500, nothing written.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_par_cb(creer_utilisateur())

    with patch(
        "Administration.admin_tenant.ecrire_la_vente_d_avoir_d_une_vente",
        side_effect=OperationalError("verrou simulé"),
    ):
        reponse = client_de_l_admin.post(
            adresse_de_l_avoir_total(vente), {"moyen_rembourse": PaymentMethod.CASH}
        )

    assert reponse.status_code == 302
    assert la_reponse_porte_un_message_d_erreur(reponse)
    assert ventes_d_avoir_de(vente) == []


def test_admin_rejouer_l_encaissement_erreur_de_la_base_message_pas_de_500(lieu):
    """
    Le rejeu échoue sur une erreur de la base (verrou) : message d'erreur, retour à la
    fiche (302), pas de page 500 ; la vente reste en attente.
    / A database error while replaying: an error message, no 500, still pending.
    """
    client_de_l_admin = client_de_l_admin_du_lieu(lieu)
    vente, _paiement = ouvrir_une_vente_stripe_en_attente_paiement_valide()

    with patch(
        "Administration.admin_tenant.encaisser_vente_stripe",
        side_effect=OperationalError("verrou simulé"),
    ):
        reponse = client_de_l_admin.post(adresse_du_rejeu_de_l_encaissement(vente))

    assert reponse.status_code == 302
    assert la_reponse_porte_un_message_d_erreur(reponse)
    vente.refresh_from_db()
    assert vente.statut == Vente.Statut.EN_ATTENTE
