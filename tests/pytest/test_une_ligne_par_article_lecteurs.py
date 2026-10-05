"""
Les lecteurs du moyen de paiement passent sur les RÈGLEMENTS de la vente, avant la
fusion « une ligne par article » (chantier 05, session H-1a).
/ The payment method readers move to the sale's PAYMENTS, before the "one line per
item" merge (chantier 05, session H-1a).

LOCALISATION : tests/pytest/test_une_ligne_par_article_lecteurs.py

RÈGLE MÉTIER TESTÉE
Bientôt, un article payé avec deux moyens sera UNE ligne et DEUX règlements, et le
moyen de la ligne (`LigneArticle.payment_method`) restera vide. Seuls les règlements
savent alors comment la vente a été payée. Tout code qui DÉCIDE quelque chose lit donc
les règlements nets de la vente et de ses ventes CORRECTION (somme par moyen) :
- la correction de moyen (D14) : elle ne modifie plus aucune ligne. Elle écrit
  seulement une vente CORRECTION, qui déplace le net du moyen corrigé (règlements
  −ancien / +nouveau, même montant). Le moyen corrigeable et son montant viennent des
  règlements nets ; deux corrections successives restent permises ; deux envois du
  même formulaire ne font qu'une correction. La vente CORRECTION garde la raison
  écrite par le caissier (champ `raison`, Q-H6), montrée dans la fiche « Vente » de
  l'admin quand elle n'est pas vide. Seules les ventes et les avoirs se corrigent
  (un retour de consigne rendu en espèces, oui ; un vidage de carte, non). Une vente
  sans argent encaissé (offerte, en points) n'a rien à corriger. Un code de moyen
  inconnu est refusé par la validation du formulaire ; un refus n'a de cible
  (`HX-Retarget`) que pour un moyen corrigeable ;
- le champ « Remboursé par » : pré-rempli seulement si la vente n'a qu'UN moyen
  d'argent net non nul, et qu'il est dans la liste du champ (espèces, CB, chèque,
  virement). Sinon : vide et obligatoire. Écrans : avoir d'une ligne, « Avoir total »,
  annulation des réservations dans l'admin, annulation d'adhésion ;
- l'admin des lignes (« Entries ») ne montre plus les champs moyen, monnaie, carte et
  portefeuille de la ligne (fiche et export). La colonne « Moyen de paiement » de la
  liste, lue sur la vente, reste ;
- le menu « Ventes & comptabilité » n'a plus l'entrée « Ancien rapport caisse ».
/ Every reader that DECIDES something reads the net payments of the sale and of its
CORRECTION sales: the correction no longer touches any line; "Refunded by" is
pre-filled only with the single net money method; the "Entries" admin hides the line's
payment fields; the old register report leaves the menu.

LA VENTE « À LA FORME DE DEMAIN »
Trois jus à 3,50 € (TVA 20 %) : UNE ligne, quantité 3, total 1050, moyen de la ligne
vide (ni monnaie, ni carte). Deux règlements : monnaie locale 500 + CB 550. Écrite par
le service de vente (`tests/pytest/fabriques_vente.py`), comme la caisse l'écrira après
la fusion. Les tests prouvent que les lecteurs marchent sur cette forme ET sur celle
d'aujourd'hui (une ligne par moyen, moyen de la ligne rempli).
/ Tomorrow's shape: ONE line, empty line method, two payments (LE 500 + CB 550).

CONTRAT DE L'ÉCRAN (ce que ces tests supposent de l'interface)
- correction, route : POST `/laboutik/paiement/corriger_moyen_paiement/` avec
  `ligne_uuid` (une ligne de la vente, pour retrouver la vente), `ancien_moyen` (LE
  moyen corrigé), `nouveau_moyen`, `raison` ; succès 200, refus 400 ;
- correction, bouton du détail (`data-testid="btn-corriger"`) : un bouton par moyen
  corrigeable au net non nul ; son adresse `hx-get` porte `ligne_uuid=<uuid>` et
  `ancien_moyen=<code du moyen>` ;
- correction, formulaire : GET `/laboutik/paiement/formulaire_correction/` avec
  `ligne_uuid` et `ancien_moyen` ; il affiche le nom du moyen et le montant
  (`data-testid="correction-montant"`), et poste le champ caché `ancien_moyen` ;
- « Remboursé par » : le champ `moyen_rembourse` du formulaire `form` des écrans de
  l'admin ; la liste `<select name="moyen_rembourse">` du formulaire d'annulation
  d'adhésion ;
- vente CORRECTION : champ `raison` (texte, vide par défaut) ; la fiche « Vente » de
  l'admin montre la raison, et aucun champ « raison » quand elle est vide ;
- export des lignes : `LigneArticleExportResource`, colonnes par leur titre.
/ Screen contract: route, detail button, form, "Refunded by" field, CORRECTION reason,
lines export.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin
(tests/PIEGES.md 13.1), rien ne reste en base de dev. La caisse est activée EN MÉMOIRE
par `configuration_modifiee()` (tests/PIEGES.md 13.22). Stripe (session, catalogue) et
Celery sont simulés (tests/PIEGES.md 13.3, 13.4). Le client est créé dans chaque test,
dans le lieu, en français (tests/PIEGES.md 13.10).
Base partagée, et non schéma dédié : aucun test ne lit un rapport, une clôture, un
numéro de vente ou la santé de la chaîne entière. Chaque test ne lit que SES ventes.
/ Rolled back per test; register module on in memory; Stripe and Celery faked; a fresh
French client per test. Each test only reads its own sales.

D'OÙ VIENNENT LES VALEURS ATTENDUES (calculées à la main)
- 3 jus à 3,50 € = 1050 → « 10,50 € » ; monnaie locale 500 + CB 550 = 1050 ;
- corriger la CB de la forme de demain déplace son net : CB −550, espèces +550 ;
- billet à 10,00 € = 1000 ; adhésion à 15,00 € = 1500.
/ Hand-computed values.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-H-retrait.md (§2, §2.1,
§5 test 6) ; CHANTIER-05-montants-entiers.md (§2, D14, D27) ; CHANTIER-05-SUIVI.md
(§4 G-1a, G-2a-bis, G-2b-bis, Q-G10 ; §5 Q-H2, Q-H6) ; briefs
CHANTIER-05-briefs/05-H-1a.md et 05-H-1-ter.md (test 9).

Lancer / Run : make test ARGS="tests/pytest/test_une_ligne_par_article_lecteurs.py"
"""

import html
import uuid as uuid_module
from decimal import Decimal
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest
from django.contrib.admin.utils import flatten_fieldsets
from django.test import Client as DjangoClient
from django.test import RequestFactory
from django.utils import translation
from django.utils.translation import gettext
from django_tenants.utils import tenant_context

from Administration.admin import dashboard
from Administration.importers.lignearticle_exporter import LigneArticleExportResource
from BaseBillet.models import (
    LigneArticle,
    PaymentMethod,
    PriceSold,
    ProductSold,
    Reservation,
    SaleOrigin,
)
from BaseBillet.models_vente import Vente
from BaseBillet.services_vente import (
    ajouter_article,
    ajouter_reglement,
    encaisser_vente,
    ouvrir_vente,
)
from comptabilite.rapport import nom_du_moyen_de_paiement
from fabriques_ecran import (
    attributs_des_elements,
    euros,
    lire_l_element,
    texte_sans_espaces_en_trop,
)
from fabriques_panier import (
    catalogue_stripe_simule,
    configuration_modifiee,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_une_adhesion_active,
    creer_utilisateur,
    taches_celery_enregistrees,
)
from fabriques_vente import (
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from laboutik.models import CorrectionPaiement
from test_avoirs_ecrivent_la_vente import lire_le_champ_rembourse_par
from test_caisse_ecrit_la_vente import (
    creer_un_article_de_caisse,
    creer_un_gobelet_et_son_retour,
    nouvelle_cle_d_idempotence,
    retrouver_la_vente_de_la_cle,
)
from test_caisse_vider_carte_deux_fedow import (
    ancien_fedow_qui_ne_connait_pas_la_carte,
    creer_une_carte_client_sans_solde,
    monnaie_cadeau_propre_au_lieu,
    monnaie_locale_propre_au_lieu,
    poser_un_solde_sur_la_carte,
    preparer_la_caisse,
    retrouver_la_vente_de_vidage,
    vider_la_carte_a_la_caisse,
)
from test_caracterisation_caisse import creer_un_point_de_vente, payer_a_la_caisse

pytestmark = pytest.mark.django_db

# Adresses de la caisse (laboutik/urls.py).
# / Register addresses.
URL_DE_LA_CORRECTION_DU_MOYEN = "/laboutik/paiement/corriger_moyen_paiement/"
URL_DU_FORMULAIRE_DE_CORRECTION = "/laboutik/paiement/formulaire_correction/"
DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE = "/laboutik/caisse/detail-vente/"

# L'en-tête d'une requête htmx (le formulaire d'annulation d'adhésion est un partiel).
# / The htmx request header (the membership cancellation form is a partial).
EN_TETE_HTMX = {"HTTP_HX_REQUEST": "true"}

# La raison que le caissier écrit dans les corrections ordinaires de ces tests.
# / The reason the cashier writes in these tests' ordinary corrections.
RAISON_ORDINAIRE = "Erreur de moyen au moment du paiement"

# Les champs de paiement d'une ligne, que l'admin des lignes ne montre plus (Q-H2).
# / The line's payment fields, no longer shown by the lines admin.
CHAMPS_DE_PAIEMENT_DE_LA_LIGNE = ["payment_method", "asset", "carte", "wallet"]


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant, mock_stripe):
    """
    Le lieu `lespass`, caisse activée en mémoire, avec Stripe (session, catalogue) et
    Celery simulés pendant tout le test.
    / The `lespass` venue, register on in memory, Stripe and Celery faked.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with catalogue_stripe_simule():
                with taches_celery_enregistrees() as taches_demandees:
                    yield SimpleNamespace(
                        tenant=tenant,
                        taches_demandees=taches_demandees,
                    )


# --------------------------------------------------------------------------
# Outils : le client, les ventes de départ
# / Helpers: the client, the starting sales
# --------------------------------------------------------------------------


def client_francais_de_l_admin_du_lieu(lieu):
    """
    Un administrateur du lieu, connecté, en français : il ouvre la caisse (sans carte
    primaire, la caisse accepte la session d'un administrateur) et l'admin. Créé dans
    le test, dans le lieu (tests/PIEGES.md 13.10).
    / A logged-in venue admin, in French: register and admin. Created inside the test.
    """
    administrateur = creer_utilisateur(prenom="Admin", nom="Lieu")
    administrateur.client_admin.add(lieu.tenant)
    client = DjangoClient(
        HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="fr"
    )
    client.force_login(administrateur)
    return client


def vendre_trois_jus_a_la_caisse(
    point_de_vente, reglements, moyen_historique_de_la_ligne=None
):
    """
    ÉTAT DE DÉPART : une vente de caisse réglée, écrite par le service de vente. UNE
    ligne : 3 jus à 3,50 € (TVA 20 %), total 1050, statut VALID. Rend la vente relue.
    / STARTING STATE: a settled register sale, ONE line of 3 juices (1050).

    - `moyen_historique_de_la_ligne` = None : le moyen de la ligne reste VIDE (ni
      monnaie, ni carte), comme après la fusion : c'est la « forme de demain » ;
    - sinon : la ligne porte ce moyen, comme la caisse l'écrit aujourd'hui.
    / None: empty line method (tomorrow's shape); otherwise the line carries it.

    :param point_de_vente: le point de vente de la vente
    :param reglements: liste de dict passés à `ajouter_reglement` (moyen, montant)
    :param moyen_historique_de_la_ligne: `PaymentMethod`, ou None (ligne au moyen vide)
    :return: la `Vente` encaissée, relue en base
    """
    article_des_jus = {
        "pricesold": creer_tarif_vendu(nom="Jus", prix_en_euros="3.50"),
        "quantite": Decimal("3"),
        "prix_unitaire": 350,
        "taux_tva": Decimal("20"),
        "status": LigneArticle.VALID,
    }
    if moyen_historique_de_la_ligne is not None:
        article_des_jus["payment_method"] = moyen_historique_de_la_ligne

    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[article_des_jus],
        reglements=reglements,
        point_de_vente=point_de_vente,
    )
    return Vente.objects.get(pk=vente.pk)


def vendre_trois_jus_a_la_forme_de_demain(point_de_vente):
    """
    ÉTAT DE DÉPART : la forme de demain. UNE ligne au moyen vide (3 jus, 1050), DEUX
    règlements : monnaie locale 500 + CB 550.
    / STARTING STATE: tomorrow's shape, one line with an empty method, LE 500 + CB 550.
    """
    return vendre_trois_jus_a_la_caisse(
        point_de_vente,
        reglements=[
            {"moyen": PaymentMethod.LOCAL_EURO, "montant": 500},
            {"moyen": PaymentMethod.CC, "montant": 550},
        ],
    )


def seul_article_de_la_vente(vente):
    """L'unique article de la vente, relu en base. / The sale's only item, read back."""
    articles_de_la_vente = list(vente.articles.all())
    assert len(articles_de_la_vente) == 1, (
        f"Attendu : un seul article, trouvé : {len(articles_de_la_vente)}."
    )
    return articles_de_la_vente[0]


def photographie_de_la_ligne(ligne):
    """
    Ce qu'une correction ne doit jamais changer sur une ligne, relu en base : ses
    champs de paiement historiques et ses montants entiers.
    / What a correction must never change on a line, read back.
    """
    ligne_relue = LigneArticle.objects.get(pk=ligne.pk)
    return {
        "payment_method": ligne_relue.payment_method,
        "asset": ligne_relue.asset,
        "carte_id": ligne_relue.carte_id,
        "wallet_id": ligne_relue.wallet_id,
        "qty": ligne_relue.qty,
        "amount": ligne_relue.amount,
        "total_catalogue": ligne_relue.total_catalogue,
        "part_offerte": ligne_relue.part_offerte,
        "total_ttc": ligne_relue.total_ttc,
        "total_ht": ligne_relue.total_ht,
        "total_tva": ligne_relue.total_tva,
    }


def reglements_de_la_vente(vente):
    """
    Les règlements de la vente, relus en base : une liste triée de paires
    (moyen, montant en centimes).
    / The sale's payments, read back: a sorted list of (method, amount) pairs.
    """
    paires_moyen_montant = []
    for reglement in vente.reglements.all():
        paires_moyen_montant.append((reglement.moyen, reglement.montant))
    return sorted(paires_moyen_montant)


def ventes_de_correction_liees_a(vente_d_origine):
    """
    Les ventes CORRECTION liées à cette vente d'origine, par numéro croissant.
    / The CORRECTION sales linked to this original sale, by increasing number.
    """
    return list(
        Vente.objects.filter(
            nature=Vente.Nature.CORRECTION,
            vente_liee=vente_d_origine,
        ).order_by("numero")
    )


# --------------------------------------------------------------------------
# Outils : les gestes du caissier
# / Helpers: the cashier's actions
# --------------------------------------------------------------------------


def corriger_le_moyen(
    client_du_caissier, ligne, ancien_moyen, nouveau_moyen, raison=RAISON_ORDINAIRE
):
    """
    Le caissier envoie le formulaire de correction, par la vraie route : la ligne (pour
    retrouver la vente), LE moyen corrigé, le nouveau moyen, la raison.
    / The cashier posts the correction form through the real route.
    """
    donnees_du_formulaire = {
        "ligne_uuid": str(ligne.uuid),
        "ancien_moyen": ancien_moyen,
        "nouveau_moyen": nouveau_moyen,
        "raison": raison,
    }
    return client_du_caissier.post(URL_DE_LA_CORRECTION_DU_MOYEN, donnees_du_formulaire)


def ouvrir_le_detail_de_la_vente(client_du_caissier, vente):
    """
    Ouvre l'écran du détail d'une vente, par l'uuid de la vente. Rend le HTML.
    / Opens a sale's detail screen by the sale's uuid. Returns its HTML.
    """
    reponse = client_du_caissier.get(
        f"{DEBUT_DE_L_URL_DU_DETAIL_D_UNE_VENTE}{vente.uuid}/"
    )
    contenu = reponse.content.decode()
    assert reponse.status_code == 200, contenu[:400]
    return contenu


class LecteurDesChampsCaches(HTMLParser):
    """
    Lit, dans une page HTML, la valeur de chaque champ `<input type="hidden">`, par son
    nom.
    / Reads the value of each hidden input of an HTML page, by its name.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.valeur_par_nom_de_champ = {}

    def handle_starttag(self, balise, attributs):
        attributs_de_la_balise = dict(attributs)
        champ_cache = (
            balise == "input" and attributs_de_la_balise.get("type") == "hidden"
        )
        if champ_cache:
            nom_du_champ = attributs_de_la_balise.get("name", "")
            self.valeur_par_nom_de_champ[nom_du_champ] = attributs_de_la_balise.get(
                "value", ""
            )


def valeur_du_champ_cache(contenu_html, nom_du_champ):
    """La valeur du champ caché `nom_du_champ`, ou None s'il est absent.
    / The value of the hidden field, or None when it is missing."""
    lecteur = LecteurDesChampsCaches()
    lecteur.feed(contenu_html)
    lecteur.close()
    return lecteur.valeur_par_nom_de_champ.get(nom_du_champ)


# --------------------------------------------------------------------------
# Outils : les écrans de l'admin
# / Helpers: the admin screens
# --------------------------------------------------------------------------


def valeur_pre_remplie_du_moyen(reponse_de_l_ecran):
    """
    La valeur affichée au départ dans le champ « Remboursé par » d'un écran de l'admin
    (formulaire `form` du contexte), et si le champ est obligatoire. Échoue si l'écran
    ne s'affiche pas ou s'il n'a pas ce champ.
    / The initial value of the "Refunded by" field of an admin screen, and whether it is
    required.

    :return: (valeur ou None, champ obligatoire)
    """
    assert reponse_de_l_ecran.status_code == 200, (
        f"L'écran ne s'affiche pas (statut {reponse_de_l_ecran.status_code})."
    )
    formulaire_de_l_ecran = reponse_de_l_ecran.context["form"]
    assert "moyen_rembourse" in formulaire_de_l_ecran.fields, (
        "L'écran n'a pas de champ « Remboursé par »."
    )
    valeur_affichee = formulaire_de_l_ecran["moyen_rembourse"].value()
    if valeur_affichee == "":
        valeur_affichee = None
    champ_obligatoire = formulaire_de_l_ecran.fields["moyen_rembourse"].required
    return valeur_affichee, champ_obligatoire


def champs_montres_par_la_fiche(reponse_de_la_fiche):
    """
    Les noms des champs qu'une fiche de l'admin montre (tous ses blocs de champs).
    / The names of the fields an admin detail page shows (all its fieldsets).
    """
    assert reponse_de_la_fiche.status_code == 200, (
        f"La fiche ne s'affiche pas (statut {reponse_de_la_fiche.status_code})."
    )
    formulaire_de_la_fiche = reponse_de_la_fiche.context["adminform"]
    return flatten_fieldsets(formulaire_de_la_fiche.fieldsets)


# ==========================================================================
# 1. LA CORRECTION DE MOYEN (D14) : seule la vente CORRECTION, lue et écrite sur
#    les règlements
# / 1. PAYMENT METHOD CORRECTION: only the CORRECTION sale, read and written on
#    the payments
# ==========================================================================


def test_correction_ne_modifie_plus_la_ligne(lieu):
    """
    Fiche H §5 test 6. Trois jus payés en espèces à la vraie caisse : une vente de
    1050, une ligne au moyen vide (Q-H2) et un règlement espèces. Le caissier
    corrige : c'était une CB. La ligne ne bouge pas : même moyen (vide), mêmes
    montants. Seule une vente CORRECTION, liée à la vente d'origine, porte la
    correction : espèces −1050, CB +1050.
    / Three juices paid in cash at the real register, corrected into CB. The line does
    not move (same empty method, same amounts); one linked CORRECTION sale:
    CASH −1050 / CB +1050.
    """
    jus = creer_un_article_de_caisse("jus", prix_en_euros="3.50", taux_tva="20.00")
    point_de_vente = creer_un_point_de_vente([jus.produit])
    client_du_caissier = client_francais_de_l_admin_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    reponse_du_paiement = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        jus,
        quantite=3,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
    )
    assert reponse_du_paiement.status_code == 200
    vente_d_origine = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    ligne_des_jus = seul_article_de_la_vente(vente_d_origine)
    assert ligne_des_jus.payment_method is None
    assert reglements_de_la_vente(vente_d_origine) == [(PaymentMethod.CASH, 1050)]
    ligne_avant_la_correction = photographie_de_la_ligne(ligne_des_jus)

    reponse = corriger_le_moyen(
        client_du_caissier, ligne_des_jus, PaymentMethod.CASH, PaymentMethod.CC
    )

    assert reponse.status_code == 200, reponse.content.decode()[:400]
    # La ligne ne bouge pas : ni son moyen, ni ses montants.
    # / The line does not move: neither its method nor its amounts.
    assert photographie_de_la_ligne(ligne_des_jus) == ligne_avant_la_correction
    ventes_de_correction = ventes_de_correction_liees_a(vente_d_origine)
    assert len(ventes_de_correction) == 1, (
        f"Attendu : une vente CORRECTION liée, trouvé : {len(ventes_de_correction)}."
    )
    vente_de_correction = ventes_de_correction[0]
    assert vente_de_correction.statut == Vente.Statut.REGLEE
    assert reglements_de_la_vente(vente_de_correction) == [
        (PaymentMethod.CASH, -1050),
        (PaymentMethod.CC, 1050),
    ]
    verifier_egalites(vente_d_origine)
    verifier_egalites(vente_de_correction)


def test_correction_d_une_vente_a_deux_moyens_deplace_le_net_du_moyen(lieu):
    """
    La forme de demain : une ligne au moyen vide, règlements monnaie locale 500 +
    CB 550. Le caissier corrige la CB en espèces (`ancien_moyen` = CB).
    La vente CORRECTION déplace le net de la CB : CB −550, espèces +550. La ligne ne
    bouge pas (moyen toujours vide, mêmes montants). La trace `CorrectionPaiement`
    est gardée : une par article de la vente (CB → espèces, avec la raison).
    / Tomorrow's shape (LE 500 + CB 550), CB corrected into cash: CORRECTION CB −550 /
    CASH +550; the line does not move; one audit trail per item.
    """
    point_de_vente = creer_un_point_de_vente([])
    client_du_caissier = client_francais_de_l_admin_du_lieu(lieu)
    vente_d_origine = vendre_trois_jus_a_la_forme_de_demain(point_de_vente)
    ligne_des_jus = seul_article_de_la_vente(vente_d_origine)
    ligne_avant_la_correction = photographie_de_la_ligne(ligne_des_jus)

    reponse = corriger_le_moyen(
        client_du_caissier, ligne_des_jus, PaymentMethod.CC, PaymentMethod.CASH
    )

    assert reponse.status_code == 200, reponse.content.decode()[:400]
    assert photographie_de_la_ligne(ligne_des_jus) == ligne_avant_la_correction
    ventes_de_correction = ventes_de_correction_liees_a(vente_d_origine)
    assert len(ventes_de_correction) == 1, (
        f"Attendu : une vente CORRECTION liée, trouvé : {len(ventes_de_correction)}."
    )
    vente_de_correction = ventes_de_correction[0]
    assert reglements_de_la_vente(vente_de_correction) == [
        (PaymentMethod.CASH, 550),
        (PaymentMethod.CC, -550),
    ]
    traces_de_la_ligne = []
    for trace in CorrectionPaiement.objects.filter(ligne_article=ligne_des_jus):
        traces_de_la_ligne.append(
            (trace.ancien_moyen, trace.nouveau_moyen, trace.raison)
        )
    assert traces_de_la_ligne == [
        (PaymentMethod.CC, PaymentMethod.CASH, RAISON_ORDINAIRE)
    ]
    verifier_egalites(vente_d_origine)
    verifier_egalites(vente_de_correction)


def test_deux_corrections_successives_suivent_les_reglements(lieu):
    """
    Une ligne au moyen VIDE, payée 1050 en espèces : seuls les règlements disent le
    moyen. Le caissier corrige espèces → CB (la route). Puis il se reprend : il ouvre
    le détail, clique le bouton « Corriger » de la CB, et le formulaire poste CB →
    chèque : la 2ᵉ correction est acceptée. Une 3ᵉ correction « espèces → CB » est
    refusée (400) : le net en espèces vaut 0. Deux ventes CORRECTION en tout :
    espèces −1050 / CB +1050, puis CB −1050 / chèque +1050. La ligne ne bouge pas.
    / A line with an EMPTY method paid in cash: CASH → CB, then CB → CHEQUE through the
    detail button and the form (accepted); a third "CASH → CB" is refused (cash net
    is 0). Two CORRECTION sales; the line does not move.
    """
    point_de_vente = creer_un_point_de_vente([])
    client_du_caissier = client_francais_de_l_admin_du_lieu(lieu)
    vente_d_origine = vendre_trois_jus_a_la_caisse(
        point_de_vente, reglements=[{"moyen": PaymentMethod.CASH, "montant": 1050}]
    )
    ligne_des_jus = seul_article_de_la_vente(vente_d_origine)
    ligne_avant_les_corrections = photographie_de_la_ligne(ligne_des_jus)

    # 1ʳᵉ correction, par la route : espèces → CB.
    # / 1st correction, through the route: cash → card.
    reponse_de_la_premiere_correction = corriger_le_moyen(
        client_du_caissier, ligne_des_jus, PaymentMethod.CASH, PaymentMethod.CC
    )
    assert reponse_de_la_premiere_correction.status_code == 200, (
        reponse_de_la_premiere_correction.content.decode()[:400]
    )

    # 2ᵉ correction, par l'écran : le bouton du détail, puis le formulaire.
    # / 2nd correction, through the screen: the detail button, then the form.
    contenu_du_detail = ouvrir_le_detail_de_la_vente(
        client_du_caissier, vente_d_origine
    )
    boutons_corriger = attributs_des_elements(contenu_du_detail, "btn-corriger")
    assert len(boutons_corriger) == 1, boutons_corriger
    adresse_du_formulaire = boutons_corriger[0].get("hx-get", "")
    assert f"ancien_moyen={PaymentMethod.CC}" in adresse_du_formulaire
    reponse_du_formulaire = client_du_caissier.get(adresse_du_formulaire)
    contenu_du_formulaire = reponse_du_formulaire.content.decode()
    assert reponse_du_formulaire.status_code == 200, contenu_du_formulaire[:400]
    ancien_moyen_poste_par_le_formulaire = valeur_du_champ_cache(
        contenu_du_formulaire, "ancien_moyen"
    )
    assert ancien_moyen_poste_par_le_formulaire == PaymentMethod.CC
    reponse_de_la_seconde_correction = corriger_le_moyen(
        client_du_caissier,
        ligne_des_jus,
        ancien_moyen_poste_par_le_formulaire,
        PaymentMethod.CHEQUE,
    )
    assert reponse_de_la_seconde_correction.status_code == 200, (
        reponse_de_la_seconde_correction.content.decode()[:400]
    )

    # 3ᵉ correction « espèces → CB » : refusée, le net en espèces vaut 0.
    # / 3rd "cash → card" correction: refused, the cash net is 0.
    reponse_de_la_troisieme_correction = corriger_le_moyen(
        client_du_caissier, ligne_des_jus, PaymentMethod.CASH, PaymentMethod.CC
    )
    assert reponse_de_la_troisieme_correction.status_code == 400

    ventes_de_correction = ventes_de_correction_liees_a(vente_d_origine)
    assert len(ventes_de_correction) == 2, (
        f"Attendu : deux ventes CORRECTION liées, trouvé : {len(ventes_de_correction)}."
    )
    assert reglements_de_la_vente(ventes_de_correction[0]) == [
        (PaymentMethod.CASH, -1050),
        (PaymentMethod.CC, 1050),
    ]
    assert reglements_de_la_vente(ventes_de_correction[1]) == [
        (PaymentMethod.CC, -1050),
        (PaymentMethod.CHEQUE, 1050),
    ]
    assert photographie_de_la_ligne(ligne_des_jus) == ligne_avant_les_corrections
    verifier_egalites(vente_d_origine)
    for vente_de_correction in ventes_de_correction:
        verifier_egalites(vente_de_correction)


def test_correction_rejouee_avec_l_ancien_moyen_perime_refusee(lieu):
    """
    La forme de demain (monnaie locale 500 + CB 550, ligne au moyen vide). Le même
    formulaire « CB → espèces » est envoyé deux fois (double clic). Le 1ᵉʳ envoi
    corrige (200) ; le 2ᵉ est refusé (400) : sous le verrou, le net de la CB vaut
    déjà 0. Une seule vente CORRECTION.
    / Tomorrow's shape: the same "CB → cash" form posted twice. The first corrects, the
    second is refused (the CB net is already 0). One CORRECTION sale only.
    """
    point_de_vente = creer_un_point_de_vente([])
    client_du_caissier = client_francais_de_l_admin_du_lieu(lieu)
    vente_d_origine = vendre_trois_jus_a_la_forme_de_demain(point_de_vente)
    ligne_des_jus = seul_article_de_la_vente(vente_d_origine)

    premiere_reponse = corriger_le_moyen(
        client_du_caissier, ligne_des_jus, PaymentMethod.CC, PaymentMethod.CASH
    )
    seconde_reponse = corriger_le_moyen(
        client_du_caissier, ligne_des_jus, PaymentMethod.CC, PaymentMethod.CASH
    )

    assert premiere_reponse.status_code == 200, premiere_reponse.content.decode()[:400]
    assert seconde_reponse.status_code == 400
    ventes_de_correction = ventes_de_correction_liees_a(vente_d_origine)
    assert len(ventes_de_correction) == 1, (
        f"Attendu : une seule vente CORRECTION, trouvé : {len(ventes_de_correction)}."
    )
    verifier_egalites(vente_d_origine)
    verifier_egalites(ventes_de_correction[0])


def test_ecran_du_detail_un_bouton_par_moyen_corrigeable(lieu):
    """
    La forme de demain (monnaie locale 500 + CB 550, ligne au moyen vide) : le détail
    propose UN seul bouton « Corriger », pour la CB. Son adresse transmet la ligne
    (pour retrouver la vente) et le moyen corrigé (`ancien_moyen=CC`). La monnaie
    locale (cashless) n'a pas de bouton.
    / Tomorrow's shape: ONE "Correct" button, for CB, carrying the line and the
    corrected method. The local currency (cashless) has none.
    """
    point_de_vente = creer_un_point_de_vente([])
    client_du_caissier = client_francais_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_a_la_forme_de_demain(point_de_vente)
    ligne_des_jus = seul_article_de_la_vente(vente)

    contenu = ouvrir_le_detail_de_la_vente(client_du_caissier, vente)

    boutons_corriger = attributs_des_elements(contenu, "btn-corriger")
    assert len(boutons_corriger) == 1, boutons_corriger
    adresse_du_bouton = boutons_corriger[0].get("hx-get", "")
    assert f"ligne_uuid={ligne_des_jus.uuid}" in adresse_du_bouton
    assert f"ancien_moyen={PaymentMethod.CC}" in adresse_du_bouton
    assert f"ancien_moyen={PaymentMethod.LOCAL_EURO}" not in contenu


def test_formulaire_de_correction_lit_le_moyen_dans_les_reglements(lieu):
    """
    La forme de demain, ligne au moyen vide. Le formulaire de correction de la CB
    affiche le moyen « Carte bancaire » et le montant de son règlement, 5,50 € (pas
    le total de la ligne, 10,50 €). Il poste `ancien_moyen` = CC.
    / Tomorrow's shape: the CB correction form shows "Carte bancaire" and 5.50 €, and
    posts `ancien_moyen` = CC.
    """
    point_de_vente = creer_un_point_de_vente([])
    client_du_caissier = client_francais_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_a_la_forme_de_demain(point_de_vente)
    ligne_des_jus = seul_article_de_la_vente(vente)

    reponse = client_du_caissier.get(
        URL_DU_FORMULAIRE_DE_CORRECTION,
        {"ligne_uuid": str(ligne_des_jus.uuid), "ancien_moyen": PaymentMethod.CC},
    )

    contenu = reponse.content.decode()
    assert reponse.status_code == 200, contenu[:400]
    texte_du_montant, _attributs = lire_l_element(contenu, "correction-montant")
    assert texte_sans_espaces_en_trop(texte_du_montant) == texte_sans_espaces_en_trop(
        euros("5,50")
    )
    with translation.override(reponse["Content-Language"]):
        nom_de_la_carte_bancaire = nom_du_moyen_de_paiement(PaymentMethod.CC)
    assert nom_de_la_carte_bancaire in contenu
    assert valeur_du_champ_cache(contenu, "ancien_moyen") == PaymentMethod.CC


def test_correction_garde_sa_raison_sur_la_vente(lieu):
    """
    Q-H6. Deux ventes en espèces (1050), chacune corrigée en CB.
    - la 1ʳᵉ avec la raison « erreur de touche » : la vente CORRECTION porte cette
      raison, et la fiche « Vente » de l'admin l'affiche ;
    - la 2ᵉ sans raison : le champ de la vente CORRECTION est vide, et la fiche ne
      montre aucun champ « raison ».
    / Q-H6: the CORRECTION sale keeps the cashier's reason, shown on the admin "Sale"
    page; without a reason the field is empty and nothing is shown.
    """
    point_de_vente = creer_un_point_de_vente([])
    client_du_caissier = client_francais_de_l_admin_du_lieu(lieu)
    vente_corrigee_avec_raison = vendre_trois_jus_a_la_caisse(
        point_de_vente,
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 1050}],
        moyen_historique_de_la_ligne=PaymentMethod.CASH,
    )
    vente_corrigee_sans_raison = vendre_trois_jus_a_la_caisse(
        point_de_vente,
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 1050}],
        moyen_historique_de_la_ligne=PaymentMethod.CASH,
    )

    reponse_avec_raison = corriger_le_moyen(
        client_du_caissier,
        seul_article_de_la_vente(vente_corrigee_avec_raison),
        PaymentMethod.CASH,
        PaymentMethod.CC,
        raison="erreur de touche",
    )
    reponse_sans_raison = corriger_le_moyen(
        client_du_caissier,
        seul_article_de_la_vente(vente_corrigee_sans_raison),
        PaymentMethod.CASH,
        PaymentMethod.CC,
        raison="",
    )

    contenu_avec_raison = reponse_avec_raison.content.decode()
    contenu_sans_raison = reponse_sans_raison.content.decode()
    assert reponse_avec_raison.status_code == 200, contenu_avec_raison[:400]
    assert reponse_sans_raison.status_code == 200, contenu_sans_raison[:400]
    correction_avec_raison = ventes_de_correction_liees_a(vente_corrigee_avec_raison)[0]
    correction_sans_raison = ventes_de_correction_liees_a(vente_corrigee_sans_raison)[0]
    assert correction_avec_raison.raison == "erreur de touche"
    assert correction_sans_raison.raison == ""

    # La fiche « Vente » de l'admin : la raison quand elle existe, rien sinon.
    # / The admin "Sale" page: the reason when there is one, nothing otherwise.
    fiche_avec_raison = client_du_caissier.get(
        f"/admin/BaseBillet/vente/{correction_avec_raison.uuid}/change/"
    )
    assert fiche_avec_raison.status_code == 200
    assert "erreur de touche" in fiche_avec_raison.content.decode()
    fiche_sans_raison = client_du_caissier.get(
        f"/admin/BaseBillet/vente/{correction_sans_raison.uuid}/change/"
    )
    champs_de_la_fiche_sans_raison = champs_montres_par_la_fiche(fiche_sans_raison)
    champs_qui_parlent_de_raison = []
    for nom_du_champ in champs_de_la_fiche_sans_raison:
        if "raison" in nom_du_champ:
            champs_qui_parlent_de_raison.append(nom_du_champ)
    assert champs_qui_parlent_de_raison == []

    verifier_egalites(correction_avec_raison)
    verifier_egalites(correction_sans_raison)


# ==========================================================================
# 2. « REMBOURSÉ PAR » PRÉ-REMPLI : le seul moyen d'argent net de la vente
# / 2. "REFUNDED BY" PRE-FILLED: the sale's single net money method
# ==========================================================================


def test_avoir_d_une_ligne_prerempli_par_le_moyen_unique_de_la_vente(lieu):
    """
    L'écran « Émettre un avoir » d'une ligne, trois ventes de 1050 :
    - ligne au moyen « espèces », réglée en espèces : pré-rempli « espèces » ;
    - forme de demain espèces 550 + monnaie locale 500 (ligne au moyen vide) : deux
      moyens d'argent (le cashless compte), champ vide et obligatoire ;
    - ligne au moyen VIDE, réglée par CB : pré-rempli « CB » (lu dans les règlements).
    Le règlement en espèces est écrit EN PREMIER : prendre le premier règlement au lieu
    du moyen unique pré-remplirait « espèces », et ce test le verrait.
    / The line credit note screen: cash line → cash; cash + LE → empty and required
    (cash written first, so "take the first payment" would be seen); empty-method line
    paid by card → card.
    """
    point_de_vente = creer_un_point_de_vente([])
    client_de_l_admin = client_francais_de_l_admin_du_lieu(lieu)
    vente_en_especes = vendre_trois_jus_a_la_caisse(
        point_de_vente,
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 1050}],
        moyen_historique_de_la_ligne=PaymentMethod.CASH,
    )
    vente_monnaie_locale_et_especes = vendre_trois_jus_a_la_caisse(
        point_de_vente,
        reglements=[
            {"moyen": PaymentMethod.CASH, "montant": 550},
            {"moyen": PaymentMethod.LOCAL_EURO, "montant": 500},
        ],
    )
    vente_par_cb_ligne_au_moyen_vide = vendre_trois_jus_a_la_caisse(
        point_de_vente, reglements=[{"moyen": PaymentMethod.CC, "montant": 1050}]
    )

    ecran_de_la_vente_en_especes = client_de_l_admin.get(
        f"/admin/BaseBillet/lignearticle/"
        f"{seul_article_de_la_vente(vente_en_especes).pk}/emettre_avoir/"
    )
    ecran_de_la_vente_a_deux_moyens = client_de_l_admin.get(
        f"/admin/BaseBillet/lignearticle/"
        f"{seul_article_de_la_vente(vente_monnaie_locale_et_especes).pk}/emettre_avoir/"
    )
    ecran_de_la_vente_par_cb = client_de_l_admin.get(
        f"/admin/BaseBillet/lignearticle/"
        f"{seul_article_de_la_vente(vente_par_cb_ligne_au_moyen_vide).pk}/emettre_avoir/"
    )

    assert valeur_pre_remplie_du_moyen(ecran_de_la_vente_en_especes) == (
        PaymentMethod.CASH,
        True,
    )
    assert valeur_pre_remplie_du_moyen(ecran_de_la_vente_a_deux_moyens) == (None, True)
    assert valeur_pre_remplie_du_moyen(ecran_de_la_vente_par_cb) == (
        PaymentMethod.CC,
        True,
    )


def test_avoir_total_prerempli_apres_une_correction(lieu):
    """
    Une vente de 1050 réglée en espèces (ligne au moyen « espèces »), puis corrigée en
    CB : une vente CORRECTION liée, espèces −1050 / CB +1050 (écrite par le service,
    comme la route l'écrit). Net : 0 en espèces, 1050 en CB. L'écran « Avoir total »
    pré-remplit « CB ».
    / A cash sale corrected into card (CORRECTION CASH −1050 / CB +1050): the full
    credit note screen pre-fills "card".
    """
    point_de_vente = creer_un_point_de_vente([])
    client_de_l_admin = client_francais_de_l_admin_du_lieu(lieu)
    vente_d_origine = vendre_trois_jus_a_la_caisse(
        point_de_vente,
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 1050}],
        moyen_historique_de_la_ligne=PaymentMethod.CASH,
    )
    vente_de_correction = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.CORRECTION,
        point_de_vente=point_de_vente,
        vente_liee=vente_d_origine,
    )
    ajouter_reglement(vente_de_correction, moyen=PaymentMethod.CASH, montant=-1050)
    ajouter_reglement(vente_de_correction, moyen=PaymentMethod.CC, montant=1050)
    encaisser_vente(vente_de_correction)

    reponse_de_l_ecran = client_de_l_admin.get(
        f"/admin/BaseBillet/vente/{vente_d_origine.uuid}/avoir_total/"
    )

    assert valeur_pre_remplie_du_moyen(reponse_de_l_ecran) == (PaymentMethod.CC, True)
    verifier_egalites(vente_d_origine)
    verifier_egalites(vente_de_correction)


def test_annulation_reservation_admin_preremplie_par_les_reglements(lieu):
    """
    Une réservation d'un billet à 10,00 €, vendue dans l'admin : sa ligne a un moyen
    VIDE, sa vente un règlement espèces de 1000. L'admin coche la réservation et lance
    « Annuler et rembourser » : l'écran pré-remplit « espèces » (lu dans les
    règlements de la vente).
    / An admin-sold ticket whose line has an EMPTY method, paid 1000 in cash: the
    reservation cancel screen pre-fills "cash", read from the sale's payments.
    """
    client_de_l_admin = client_francais_de_l_admin_du_lieu(lieu)
    billetterie = creer_evenement_avec_tarif(prix="10.00")
    produit_vendu = ProductSold.objects.create(
        product=billetterie.produit, event=billetterie.evenement
    )
    tarif_vendu = PriceSold.objects.create(
        productsold=produit_vendu, price=billetterie.tarif, prix=billetterie.tarif.prix
    )
    reservation = Reservation.objects.create(
        user_commande=creer_utilisateur(),
        event=billetterie.evenement,
        status=Reservation.VALID,
    )
    vente_du_billet = fabriquer_vente_encaissee(
        origine=SaleOrigin.ADMIN,
        articles=[
            {
                "pricesold": tarif_vendu,
                "quantite": Decimal("1"),
                "prix_unitaire": 1000,
                "taux_tva": Decimal("0"),
                "reservation": reservation,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 1000}],
    )
    assert seul_article_de_la_vente(vente_du_billet).payment_method is None

    reponse_de_l_ecran = client_de_l_admin.post(
        "/admin/BaseBillet/reservation/",
        {
            "action": "action_cancel_refund_reservations",
            "_selected_action": [str(reservation.pk)],
        },
    )

    assert valeur_pre_remplie_du_moyen(reponse_de_l_ecran) == (PaymentMethod.CASH, True)
    verifier_egalites(vente_du_billet)


def test_annulation_adhesion_preremplie_par_les_reglements(lieu):
    """
    Une adhésion à 15,00 € vendue dans l'admin : sa ligne a un moyen VIDE, sa vente un
    règlement espèces de 1500. L'admin ouvre « Annuler l'adhésion » : la liste
    « Remboursé par » a « espèces » sélectionné (lu dans les règlements de la vente).
    / A membership whose line has an EMPTY method, paid 1500 in cash: the membership
    cancellation form pre-selects "cash", read from the sale's payments.
    """
    client_de_l_admin = client_francais_de_l_admin_du_lieu(lieu)
    produit_adhesion = creer_adhesion(prix="15.00")
    adhesion = creer_une_adhesion_active(creer_utilisateur(), produit_adhesion)
    produit_vendu = ProductSold.objects.create(product=produit_adhesion.produit)
    tarif_vendu = PriceSold.objects.create(
        productsold=produit_vendu,
        price=produit_adhesion.tarif,
        prix=produit_adhesion.tarif.prix,
    )
    vente_de_l_adhesion = fabriquer_vente_encaissee(
        origine=SaleOrigin.ADMIN,
        articles=[
            {
                "pricesold": tarif_vendu,
                "quantite": Decimal("1"),
                "prix_unitaire": 1500,
                "taux_tva": Decimal("0"),
                "membership": adhesion,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 1500}],
    )
    assert seul_article_de_la_vente(vente_de_l_adhesion).payment_method is None

    reponse_du_formulaire = client_de_l_admin.get(
        f"/memberships/{adhesion.pk}/cancel/", **EN_TETE_HTMX
    )

    assert reponse_du_formulaire.status_code == 200
    champ_rembourse_par = lire_le_champ_rembourse_par(reponse_du_formulaire)
    assert champ_rembourse_par.champ_present
    assert champ_rembourse_par.moyen_pre_rempli == PaymentMethod.CASH
    verifier_egalites(vente_de_l_adhesion)


# ==========================================================================
# 3. L'ADMIN DES LIGNES ET LE MENU (Q-H2)
# / 3. THE LINES ADMIN AND THE MENU
# ==========================================================================


def test_fiche_d_une_ligne_sans_champs_de_paiement(lieu):
    """
    « Entries » (l'admin des lignes), une ligne réglée en espèces :
    - sa fiche ne montre ni le moyen, ni la monnaie, ni la carte, ni le portefeuille
      de la ligne ;
    - la liste garde sa colonne « Moyen de paiement », lue sur la vente ;
    - l'export n'exporte aucun champ de paiement de la ligne (moyen, monnaie, carte,
      portefeuille), quel que soit le titre de la colonne : on lit l'attribut de
      chaque champ exporté, pas seulement son titre ; il garde « Moyens de la vente »
      (lu sur la vente).
    / "Entries": the line page hides the line's payment fields; the list keeps its
    "Payment method" column (read on the sale); the export carries no payment field
    of the line, whatever the column title.
    """
    point_de_vente = creer_un_point_de_vente([])
    client_de_l_admin = client_francais_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_a_la_caisse(
        point_de_vente,
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 1050}],
        moyen_historique_de_la_ligne=PaymentMethod.CASH,
    )
    ligne_des_jus = seul_article_de_la_vente(vente)

    reponse_de_la_fiche = client_de_l_admin.get(
        f"/admin/BaseBillet/lignearticle/{ligne_des_jus.pk}/change/"
    )
    reponse_de_la_liste = client_de_l_admin.get("/admin/BaseBillet/lignearticle/")
    with translation.override("fr"):
        donnees_exportees = LigneArticleExportResource().export(
            LigneArticle.objects.filter(pk=ligne_des_jus.pk)
        )
        titres_des_colonnes_exportees = []
        for titre_de_la_colonne in donnees_exportees.headers:
            titres_des_colonnes_exportees.append(str(titre_de_la_colonne))
        titre_de_la_colonne_carte = gettext("Carte cashless")
        titre_de_la_colonne_portefeuille = gettext("Wallet from")
        titre_de_la_colonne_des_moyens = gettext("Moyens de la vente")

    # La fiche : aucun champ de paiement de la ligne.
    # / The page: no payment field of the line.
    champs_de_la_fiche = champs_montres_par_la_fiche(reponse_de_la_fiche)
    champs_de_paiement_montres = []
    for nom_du_champ in CHAMPS_DE_PAIEMENT_DE_LA_LIGNE:
        if nom_du_champ in champs_de_la_fiche:
            champs_de_paiement_montres.append(nom_du_champ)
    assert champs_de_paiement_montres == []

    # La liste : la colonne lue sur la vente reste.
    # / The list: the column read on the sale stays.
    assert reponse_de_la_liste.status_code == 200
    assert "moyens_de_paiement" in reponse_de_la_liste.context["cl"].list_display

    # L'export : ni carte, ni portefeuille ; les moyens de la vente restent.
    # / The export: no card, no wallet; the sale's methods stay.
    assert titre_de_la_colonne_carte not in titres_des_colonnes_exportees
    assert titre_de_la_colonne_portefeuille not in titres_des_colonnes_exportees
    assert titre_de_la_colonne_des_moyens in titres_des_colonnes_exportees

    # L'export, champ par champ : aucun ne lit un champ de paiement de la ligne,
    # ni par son attribut, ni par un titre de colonne qui reprend le nom du champ
    # (un champ ajouté à `Meta.fields` prend son nom comme titre).
    # / The export, field by field: none reads a line payment field, by attribute or
    # by a column title equal to the field name.
    champs_de_paiement_exportes = []
    for champ_exporte in LigneArticleExportResource().get_export_fields():
        attribut_du_champ = champ_exporte.attribute
        titre_du_champ = str(champ_exporte.column_name)
        if attribut_du_champ in CHAMPS_DE_PAIEMENT_DE_LA_LIGNE:
            champs_de_paiement_exportes.append(attribut_du_champ)
        if titre_du_champ in CHAMPS_DE_PAIEMENT_DE_LA_LIGNE:
            champs_de_paiement_exportes.append(titre_du_champ)
    assert champs_de_paiement_exportes == []
    verifier_egalites(vente)


def test_menu_sans_ancien_rapport_caisse(lieu):
    """
    Module caisse actif : aucune section du menu ne mène à l'ancienne clôture de la
    caisse, et aucune entrée ne s'appelle « Ancien rapport caisse ».
    / Register module on: no menu section links to the old register closures, and no
    entry is called "Ancien rapport caisse".
    """
    # L'ancienne clôture de la caisse n'est plus enregistrée dans l'admin : son adresse
    # est écrite en clair, `reverse()` ne la trouverait plus.
    # / The old POS closure is no longer registered: its address is written out.
    lien_de_l_ancien_rapport_caisse = "/admin/laboutik/cloturecaisse/"

    sections_du_menu = dashboard._construire_sections_modules(
        RequestFactory().get("/admin/")
    )

    titre_de_l_ancienne_entree = gettext("Ancien rapport caisse")
    entrees_vers_l_ancien_rapport = []
    for section in sections_du_menu:
        for entree in section.get("items", []):
            mene_a_l_ancien_rapport = (
                str(entree.get("link")) == lien_de_l_ancien_rapport_caisse
            )
            porte_l_ancien_titre = (
                str(entree.get("title")) == titre_de_l_ancienne_entree
            )
            if mene_a_l_ancien_rapport or porte_l_ancien_titre:
                entrees_vers_l_ancien_rapport.append(
                    (str(section.get("title")), str(entree.get("title")))
                )
    assert entrees_vers_l_ancien_rapport == []


# ==========================================================================
# 4. CE QUE LA CORRECTION REFUSE : la nature de la vente, l'argent jamais reçu,
#    un moyen inconnu
# / 4. WHAT THE CORRECTION REFUSES: the sale's nature, money never received, an
#    unknown method
# ==========================================================================


def nombre_de_ventes_de_correction_liees_a(vente_d_origine):
    """Le nombre de ventes CORRECTION liées à cette vente.
    / The number of CORRECTION sales linked to this sale."""
    return Vente.objects.filter(
        nature=Vente.Nature.CORRECTION, vente_liee=vente_d_origine
    ).count()


def nombre_de_traces_de_correction_de_la_vente(vente):
    """Le nombre de traces `CorrectionPaiement` écrites sur les articles de cette vente.
    / The number of `CorrectionPaiement` traces written on this sale's items."""
    return CorrectionPaiement.objects.filter(ligne_article__vente=vente).count()


def test_vidage_de_carte_jamais_corrigeable(lieu):
    """
    Le caissier vide, par la vraie route de la caisse, une carte qui porte 5,00 € de
    monnaie locale et 2,00 € de jetons cadeau (lieu non relié à l'ancien Fedow). La
    vente VIDAGE_CARTE rend 5,00 € en espèces (règlement espèces −500) et reprend les
    jetons (un article « Jetons cadeau repris au vidage », un règlement « jetons »).
    Un vidage n'est pas une vente qu'on corrige : seules les ventes et les avoirs se
    corrigent.
    - le détail de la vente ne propose aucun bouton « Corriger » ;
    - un POST forgé espèces → CB, sur la ligne des jetons repris, est refusé (400) ;
      aucune vente CORRECTION n'est écrite.
    / A real card emptying (cash given back, gift tokens taken back): no Correct
    button, and a forged cash → card POST is refused, no CORRECTION sale.
    """
    caisse = preparer_la_caisse(lieu)
    carte_du_client = creer_une_carte_client_sans_solde(lieu)
    poser_un_solde_sur_la_carte(
        carte_du_client, monnaie_locale_propre_au_lieu(lieu), 500
    )
    poser_un_solde_sur_la_carte(
        carte_du_client, monnaie_cadeau_propre_au_lieu(lieu), 200
    )
    reponse_du_vidage, _classe_fedow_api = vider_la_carte_a_la_caisse(
        caisse,
        carte_du_client,
        ancien_fedow_qui_ne_connait_pas_la_carte(),
        lieu_relie=False,
    )
    assert reponse_du_vidage.status_code == 200
    vente_de_vidage = retrouver_la_vente_de_vidage(carte_du_client)
    # L'état de départ : de l'argent rendu en espèces, et un article (les jetons).
    # / Starting state: cash given back, and one item (the tokens).
    moyens_et_montants_du_vidage = []
    for reglement in vente_de_vidage.reglements.all():
        moyens_et_montants_du_vidage.append((reglement.moyen, reglement.montant))
    assert (PaymentMethod.CASH, -500) in moyens_et_montants_du_vidage
    ligne_des_jetons_repris = seul_article_de_la_vente(vente_de_vidage)

    contenu_du_detail = ouvrir_le_detail_de_la_vente(
        caisse.client_du_caissier, vente_de_vidage
    )
    reponse_forgee = corriger_le_moyen(
        caisse.client_du_caissier,
        ligne_des_jetons_repris,
        PaymentMethod.CASH,
        PaymentMethod.CC,
    )

    boutons_corriger = attributs_des_elements(contenu_du_detail, "btn-corriger")
    assert boutons_corriger == []
    assert reponse_forgee.status_code == 400
    assert nombre_de_ventes_de_correction_liees_a(vente_de_vidage) == 0
    verifier_egalites(vente_de_vidage)


def test_retour_de_consigne_en_especes_reste_corrigeable(lieu):
    """
    Un retour de consigne au comptoir, par la vraie route de la caisse : une vente
    AVOIR, 1,00 € rendu en espèces (règlement espèces −100). Un avoir de caisse en
    espèces se corrige : le détail propose UN bouton « Corriger » (espèces), et la
    correction en CB passe (200). La vente CORRECTION déplace le net des espèces :
    espèces +100, CB −100.
    / A real deposit return refunded in cash (AVOIR, cash −100): one Correct button,
    and the correction into card goes through (cash +100 / card −100).
    """
    consigne = creer_un_gobelet_et_son_retour(lieu)
    point_de_vente = creer_un_point_de_vente([consigne.retour.produit])
    client_du_caissier = client_francais_de_l_admin_du_lieu(lieu)
    cle_d_idempotence = nouvelle_cle_d_idempotence()
    reponse_du_retour = payer_a_la_caisse(
        client_du_caissier,
        point_de_vente,
        consigne.retour,
        quantite=1,
        moyen_de_paiement="espece",
        autres_champs={"cle_idempotence_paiement": cle_d_idempotence},
    )
    assert reponse_du_retour.status_code == 200
    vente_du_retour = retrouver_la_vente_de_la_cle(cle_d_idempotence)
    assert vente_du_retour.nature == Vente.Nature.AVOIR
    assert reglements_de_la_vente(vente_du_retour) == [(PaymentMethod.CASH, -100)]
    ligne_du_retour = seul_article_de_la_vente(vente_du_retour)

    contenu_du_detail = ouvrir_le_detail_de_la_vente(
        client_du_caissier, vente_du_retour
    )
    reponse = corriger_le_moyen(
        client_du_caissier, ligne_du_retour, PaymentMethod.CASH, PaymentMethod.CC
    )

    boutons_corriger = attributs_des_elements(contenu_du_detail, "btn-corriger")
    assert len(boutons_corriger) == 1, boutons_corriger
    assert f"ancien_moyen={PaymentMethod.CASH}" in boutons_corriger[0].get("hx-get", "")
    assert reponse.status_code == 200, reponse.content.decode()[:400]
    ventes_de_correction = ventes_de_correction_liees_a(vente_du_retour)
    assert len(ventes_de_correction) == 1
    assert reglements_de_la_vente(ventes_de_correction[0]) == [
        (PaymentMethod.CASH, 100),
        (PaymentMethod.CC, -100),
    ]
    verifier_egalites(vente_du_retour)
    verifier_egalites(ventes_de_correction[0])


def test_post_force_sur_une_vente_offerte_ou_en_points_refuse(lieu):
    """
    Deux ventes de caisse réglées, qui n'ont encaissé aucun argent :
    - une bière à 5,00 € entièrement offerte (un règlement « offert » de 500) ;
    - un pin's à 300 points, dans une vente en points (un règlement « points ou
      temps » de 300).
    Un POST forgé « espèces → CB » sur chacune est refusé (400). Aucune vente
    CORRECTION ni trace `CorrectionPaiement` n'est écrite : il n'y a pas d'espèces à
    déplacer (net des espèces nul).
    / Two settled register sales without money (fully offered, points): a forged
    "cash → card" POST is refused on each, no CORRECTION sale, no CorrectionPaiement.
    """
    point_de_vente = creer_un_point_de_vente([])
    client_du_caissier = client_francais_de_l_admin_du_lieu(lieu)
    vente_offerte = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        point_de_vente=point_de_vente,
        articles=[
            {
                "pricesold": creer_tarif_vendu(nom="Biere", prix_en_euros="5.00"),
                "quantite": Decimal("1"),
                "prix_unitaire": 500,
                "taux_tva": Decimal("20"),
                "offert_en_totalite": True,
                "status": LigneArticle.VALID,
            }
        ],
    )
    assert reglements_de_la_vente(vente_offerte) == [(PaymentMethod.FREE, 500)]

    # La vente en points : son unité est une monnaie de points (un uuid), pas l'euro.
    # La fabrique n'a pas de paramètre d'unité : on passe par le service.
    # / The points sale: its unit is a points currency (a uuid), through the service.
    vente_en_points_a_encaisser = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.VENTE,
        unite=str(uuid_module.uuid4()),
        point_de_vente=point_de_vente,
    )
    ajouter_article(
        vente_en_points_a_encaisser,
        pricesold=creer_tarif_vendu(nom="Pins", prix_en_euros="3.00"),
        quantite=Decimal("1"),
        prix_unitaire=300,
        taux_tva=Decimal("0"),
        status=LigneArticle.VALID,
    )
    ajouter_reglement(
        vente_en_points_a_encaisser, moyen=PaymentMethod.NON_MONETAIRE, montant=300
    )
    vente_en_points = encaisser_vente(vente_en_points_a_encaisser)

    reponse_sur_la_vente_offerte = corriger_le_moyen(
        client_du_caissier,
        seul_article_de_la_vente(vente_offerte),
        PaymentMethod.CASH,
        PaymentMethod.CC,
    )
    reponse_sur_la_vente_en_points = corriger_le_moyen(
        client_du_caissier,
        seul_article_de_la_vente(vente_en_points),
        PaymentMethod.CASH,
        PaymentMethod.CC,
    )

    assert reponse_sur_la_vente_offerte.status_code == 400
    assert reponse_sur_la_vente_en_points.status_code == 400
    assert nombre_de_ventes_de_correction_liees_a(vente_offerte) == 0
    assert nombre_de_ventes_de_correction_liees_a(vente_en_points) == 0
    assert nombre_de_traces_de_correction_de_la_vente(vente_offerte) == 0
    assert nombre_de_traces_de_correction_de_la_vente(vente_en_points) == 0
    verifier_egalites(vente_offerte)
    verifier_egalites(vente_en_points)


def test_ancien_moyen_inconnu_refuse_sans_cible(lieu):
    """
    Une vente de 10,50 € en espèces. Deux POST forgés :
    - `ancien_moyen=ZZ` (aucun moyen de paiement ne porte ce code) : refusé par la
      validation du formulaire (400), avant toute règle métier : la réponse ne porte
      pas le refus métier « Seul un paiement en espèces… », ni de cible
      (`HX-Retarget`) ;
    - `ancien_moyen=LE` (monnaie locale, cashless) : refusé (400) par la règle
      métier « Les paiements cashless ne peuvent pas être modifiés », sans cible :
      la zone d'un formulaire n'existe que pour un moyen corrigeable.
    Aucune vente CORRECTION ni trace `CorrectionPaiement` n'est écrite.
    / Forged POSTs: an unknown code is refused by the form validation, a cashless code
    by the business rule; neither carries an HX-Retarget; no CORRECTION sale, no
    CorrectionPaiement.
    """
    point_de_vente = creer_un_point_de_vente([])
    client_du_caissier = client_francais_de_l_admin_du_lieu(lieu)
    vente = vendre_trois_jus_a_la_caisse(
        point_de_vente,
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 1050}],
        moyen_historique_de_la_ligne=PaymentMethod.CASH,
    )
    ligne_des_jus = seul_article_de_la_vente(vente)

    reponse_au_code_inconnu = corriger_le_moyen(
        client_du_caissier, ligne_des_jus, "ZZ", PaymentMethod.CC
    )
    reponse_au_moyen_cashless = corriger_le_moyen(
        client_du_caissier, ligne_des_jus, PaymentMethod.LOCAL_EURO, PaymentMethod.CC
    )

    with translation.override(reponse_au_moyen_cashless["Content-Language"]):
        refus_metier_des_moyens = gettext(
            "Seul un paiement en espèces, par carte bancaire ou par chèque "
            "peut être corrigé."
        )
        refus_metier_du_cashless = gettext(
            "Les paiements cashless ne peuvent pas etre modifies"
        )
    contenu_au_code_inconnu = html.unescape(reponse_au_code_inconnu.content.decode())
    contenu_au_moyen_cashless = html.unescape(
        reponse_au_moyen_cashless.content.decode()
    )
    assert reponse_au_code_inconnu.status_code == 400
    assert refus_metier_des_moyens not in contenu_au_code_inconnu
    assert "HX-Retarget" not in reponse_au_code_inconnu
    assert reponse_au_moyen_cashless.status_code == 400
    assert refus_metier_du_cashless in contenu_au_moyen_cashless
    assert "HX-Retarget" not in reponse_au_moyen_cashless
    assert nombre_de_ventes_de_correction_liees_a(vente) == 0
    assert nombre_de_traces_de_correction_de_la_vente(vente) == 0
    verifier_egalites(vente)
