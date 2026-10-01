"""
Tests des AVOIRS émis dans l'admin : chaque avoir est une `Vente` de nature AVOIR,
écrite par le service de vente, liée à la vente d'origine, et encaissée.
/ Credit notes issued in the admin: every credit note is an AVOIR `Vente`, written by
the sale service, linked to the original sale, and settled.

LOCALISATION : tests/pytest/test_avoirs_ecrivent_la_vente.py

LA RÈGLE TESTÉE
L'admin clique « Avoir » sur une ligne de vente (liste des ventes). Un écran s'ouvre
(GET) ; l'admin le valide (POST). L'avoir est alors :
- une vente AVOIR, origine ADMIN, liée à la vente de la ligne (`vente_liee`, vide pour
  une ligne écrite avant le chantier), client = celui de la vente liée ;
- un article : même tarif vendu, même prix unitaire, quantité NÉGATIVE, même taux de
  TVA, part offerte recopiée en négatif (fonction `ajouter_l_article_d_avoir` du
  service) ;
- UN règlement d'argent du net rendu, s'il n'est pas nul, au moyen « Remboursé par »
  choisi (espèces, CB, chèque, virement) ; un règlement FREE négatif pour la part
  offerte, s'il y en a une, écrit une seule fois ;
- encaissé, PUIS la ligne d'avoir passe CREDIT_NOTE (déclencheur de l'ancien LaBoutik) ;
  tout ou rien.
Trois écrans :
- ligne hors Stripe, pas entièrement offerte : champ « Remboursé par », pré-rempli avec
  le moyen d'origine s'il est dans la liste, sinon vide et obligatoire ;
- ligne entièrement offerte (part offerte = total catalogue, non nul) : pas de champ,
  un seul règlement FREE négatif ;
- ligne payée par Stripe : pas de champ, l'écran prévient « Remboursez cette somme
  depuis votre tableau de bord Stripe. », aucun appel à Stripe, règlement négatif au
  moyen Stripe d'origine, sans référence externe.
/ The admin opens the "credit note" screen (GET) and confirms it (POST): one AVOIR sale,
linked, one item mirrored with a negative quantity, one money payment at the chosen
"Refunded by" method, one FREE payment for the offered part, settled, then CREDIT_NOTE.

CONTRAT DE L'ÉCRAN (ce que ces tests supposent de l'interface)
- URL : `/admin/BaseBillet/lignearticle/<pk>/emettre_avoir/`, GET = écran (200),
  POST = action (302 si l'avoir est émis) ;
- le contexte de l'écran porte `form`, un formulaire Django ; il a le champ
  `moyen_rembourse` seulement pour une ligne hors Stripe pas entièrement offerte ;
- formulaire refusé (champ vide) : l'écran est rendu de nouveau (200), rien n'est écrit.
/ Screen contract: GET = 200 screen with a `form` context; `moyen_rembourse` field only
for a non-Stripe, not fully offered line; POST = 302; refused form = 200, nothing written.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin, aucune vente
scellée ne reste en base de dev (tests/PIEGES.md 13.1). Stripe (session, catalogue,
remboursement) et Celery sont simulés : aucun appel réseau, aucune tâche envoyée.
/ Rolled-back transaction per test. Stripe (including refunds) and Celery are faked.

CODE PARCOURU / CODE EXERCISED
- Administration/admin_tenant.py — LigneArticleAdmin.emettre_avoir (écran et action) ;
- BaseBillet/services_vente.py — ajouter_l_article_d_avoir, ouvrir_vente,
  ajouter_reglement, encaisser_vente.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-D-en-ligne-avoirs.md (§4,
§5 tests 18, 18b, 18c, 19) ; CHANTIER-05-SUIVI.md §4 (D-3) ; brief
CHANTIER-05-briefs/05-D-3a.md.

Lancer / Run : make test ARGS="tests/pytest/test_avoirs_ecrivent_la_vente.py"
"""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.messages import get_messages
from django_tenants.utils import tenant_context

from BaseBillet import services_vente
from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
from BaseBillet.models_vente import Reglement, Vente
from fabriques_panier import (
    catalogue_stripe_simule,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    taches_celery_enregistrees,
)
from fabriques_vente import (
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from test_admin_ecrit_la_vente import (
    encaissement_qui_echoue,
    moyens_et_montants_des_reglements,
    statuts_des_articles_a_l_encaissement,
    vendre_et_relire,
)
from test_caracterisation_annulations import acheter_des_billets_payes_par_stripe
from test_caracterisation_en_ligne import creer_un_administrateur_du_lieu

pytestmark = pytest.mark.django_db

# Le message de l'écran d'une ligne payée par Stripe (msgid français).
# / The screen message for a Stripe-paid line (French msgid).
MESSAGE_REMBOURSEMENT_STRIPE_A_LA_MAIN = (
    "Remboursez cette somme depuis votre tableau de bord Stripe."
)

# Le refus d'un avoir quand la vente d'origine n'est pas réglée (msgid français).
# / The refusal when the original sale is not settled (French msgid).
MESSAGE_VENTE_D_ORIGINE_PAS_REGLEE = (
    "La vente d'origine n'est pas réglée : l'avoir est impossible."
)

# Les moyens proposés par le champ « Remboursé par » : espèces, CB, chèque, virement.
# / The methods offered by the "Refunded by" field: cash, card, cheque, transfer.
MOYENS_DU_CHAMP_REMBOURSE_PAR = [
    PaymentMethod.CASH,
    PaymentMethod.CC,
    PaymentMethod.CHEQUE,
    PaymentMethod.TRANSFER,
]


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant, mock_stripe):
    """
    Le lieu `lespass`, avec Stripe (session, catalogue, remboursement) et Celery simulés
    pendant tout le test.
    / The `lespass` venue, with Stripe (session, catalogue, refund) and Celery faked.

    `remboursement_stripe` remplace `stripe.Refund.create` : on compte ses appels.
    / `remboursement_stripe` replaces `stripe.Refund.create`: its calls are counted.
    """
    remboursement_reussi = MagicMock(status="succeeded")
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees() as taches_demandees:
                with patch(
                    "stripe.Refund.create", return_value=remboursement_reussi
                ) as remboursement_stripe:
                    yield SimpleNamespace(
                        tenant=tenant,
                        stripe=mock_stripe,
                        taches_demandees=taches_demandees,
                        remboursement_stripe=remboursement_stripe,
                    )


# --------------------------------------------------------------------------
# Gestes de l'admin
# / Admin actions
# --------------------------------------------------------------------------


def url_de_l_avoir(ligne):
    """L'adresse du bouton « Avoir » d'une ligne de vente.
    / The address of the "Credit note" button of a sale line."""
    return f"/admin/BaseBillet/lignearticle/{ligne.pk}/emettre_avoir/"


def ouvrir_l_ecran_de_l_avoir(client_de_l_admin, ligne):
    """L'admin clique « Avoir » : l'écran « Émettre un avoir » s'ouvre (GET).
    / The admin clicks "Credit note": the screen opens (GET)."""
    return client_de_l_admin.get(url_de_l_avoir(ligne))


def valider_l_ecran_de_l_avoir(client_de_l_admin, ligne, moyen_rembourse=None):
    """
    L'admin valide l'écran (POST), avec le moyen « Remboursé par » choisi s'il y en a
    un. Sans moyen, le formulaire est envoyé sans ce champ.
    / The admin confirms the screen (POST), with the chosen "Refunded by" method if any.
    """
    donnees_du_formulaire = {}
    if moyen_rembourse is not None:
        donnees_du_formulaire["moyen_rembourse"] = moyen_rembourse
    return client_de_l_admin.post(url_de_l_avoir(ligne), donnees_du_formulaire)


# --------------------------------------------------------------------------
# Assistants de lecture
# / Reading helpers
# --------------------------------------------------------------------------


def champs_du_formulaire_de_l_ecran(reponse_de_l_ecran):
    """
    Les champs du formulaire de l'écran d'avoir (contexte `form`). Échoue si l'écran ne
    s'est pas affiché.
    / The fields of the credit note screen's form. Fails if the screen did not show.
    """
    assert reponse_de_l_ecran.status_code == 200, (
        f"L'écran d'avoir ne s'affiche pas (statut {reponse_de_l_ecran.status_code})."
    )
    formulaire_de_l_ecran = reponse_de_l_ecran.context["form"]
    return formulaire_de_l_ecran.fields


def valeur_pre_remplie_du_moyen(reponse_de_l_ecran):
    """La valeur affichée au départ dans le champ « Remboursé par ».
    / The value initially shown in the "Refunded by" field."""
    formulaire_de_l_ecran = reponse_de_l_ecran.context["form"]
    return formulaire_de_l_ecran["moyen_rembourse"].value()


def textes_des_messages_de_l_admin(reponse):
    """Les messages que l'action a laissés à l'admin (framework `messages`).
    / The messages the action left for the admin."""
    textes = []
    for message in get_messages(reponse.wsgi_request):
        textes.append(str(message))
    return textes


def l_avoir_de_la_ligne(ligne):
    """La ligne d'avoir émise pour cette ligne de vente (une seule).
    / The credit note line issued for this sale line (only one)."""
    return LigneArticle.objects.get(credit_note_for=ligne)


def verifier_la_vente_d_avoir_encaissee(avoir, vente_liee_attendue, client_attendu):
    """
    Relit la vente de la ligne d'avoir et vérifie la règle commune : nature AVOIR,
    origine ADMIN, REGLEE, numérotée, liée à la vente d'origine, client attendu.
    / Reads the credit note's sale back: AVOIR, ADMIN, settled, numbered, linked, client.

    :return: la vente d'avoir relue
    """
    assert avoir.vente_id is not None, "La ligne d'avoir n'a pas de vente."
    vente_d_avoir = Vente.objects.get(pk=avoir.vente_id)
    assert vente_d_avoir.nature == Vente.Nature.AVOIR
    assert vente_d_avoir.origine == SaleOrigin.ADMIN
    assert vente_d_avoir.statut == Vente.Statut.REGLEE, (
        f"La vente d'avoir n'est pas encaissée (statut {vente_d_avoir.statut})."
    )
    assert vente_d_avoir.numero is not None
    assert vente_d_avoir.vente_liee == vente_liee_attendue
    assert vente_d_avoir.client == client_attendu
    return vente_d_avoir


def rien_n_est_ecrit_pour_la_ligne(ligne):
    """
    Vérifie qu'aucun avoir n'existe pour la ligne : aucune ligne d'avoir, aucune vente
    AVOIR liée à sa vente, aucun règlement négatif ; la ligne garde son statut VALID.
    / Checks no credit note exists for the line: no line, no linked AVOIR sale, no
    negative payment; the line stays VALID.
    """
    assert not LigneArticle.objects.filter(credit_note_for=ligne).exists()
    ligne.refresh_from_db()
    assert ligne.status == LigneArticle.VALID
    if ligne.vente_id is not None:
        assert not Vente.objects.filter(
            nature=Vente.Nature.AVOIR, vente_liee_id=ligne.vente_id
        ).exists()
        assert not Reglement.objects.filter(
            vente__vente_liee_id=ligne.vente_id, montant__lt=0
        ).exists()


# --------------------------------------------------------------------------
# États de départ écrits par le service de vente
# / Starting states written by the sale service
# --------------------------------------------------------------------------


def vendre_a_la_caisse_un_article_paye_en_monnaie_locale():
    """
    ÉTAT DE DÉPART : une vente de caisse réglée, un article à 5 € payé en monnaie
    locale (`LE`, cashless). Écrite par le service de vente, comme la caisse l'écrit.
    Rend la ligne de l'article.
    / STARTING STATE: a settled register sale, one 5 € item paid in local currency (LE).
    """
    tarif_vendu = creer_tarif_vendu(nom="Bière", prix_en_euros="5.00")
    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": tarif_vendu,
                "quantite": Decimal("1"),
                "prix_unitaire": 500,
                "taux_tva": Decimal("20"),
                "payment_method": PaymentMethod.LOCAL_EURO,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[{"moyen": PaymentMethod.LOCAL_EURO, "montant": 500}],
    )
    return vente.articles.get()


def vendre_a_la_caisse_une_biere_en_deux_parts():
    """
    ÉTAT DE DÉPART : une bière à 5 € payée 3 € en jetons cadeau (`LG`) et 2 € par CB,
    écrite en DEUX PARTS comme la caisse en cascade l'écrit
    (`laboutik/views.py` `_creer_lignes_articles_cascade`) :
    - part « jetons » : quantité 0,6, total catalogue imposé 300, entièrement offerte
      (source JETONS), moyen historique LG ;
    - part « CB » : quantité 0,4, total catalogue imposé 200, moyen historique CC.
    Règlements : LG 300, CB 200. Rend les deux parts.
    / STARTING STATE: a 5 € beer paid 3 € in gift tokens and 2 € by card, written in
    two parts like the cascade register writes it.
    """
    tarif_vendu = creer_tarif_vendu(nom="Bière", prix_en_euros="5.00")
    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": tarif_vendu,
                "quantite": Decimal("0.6"),
                "prix_unitaire": 500,
                "taux_tva": Decimal("20"),
                "total_catalogue_impose": 300,
                "part_offerte": 300,
                "source_offert": LigneArticle.SourceOffert.JETONS,
                "payment_method": PaymentMethod.LOCAL_GIFT,
                "status": LigneArticle.VALID,
            },
            {
                "pricesold": tarif_vendu,
                "quantite": Decimal("0.4"),
                "prix_unitaire": 500,
                "taux_tva": Decimal("20"),
                "total_catalogue_impose": 200,
                "payment_method": PaymentMethod.CC,
                "status": LigneArticle.VALID,
            },
        ],
        reglements=[
            {"moyen": PaymentMethod.LOCAL_GIFT, "montant": 300},
            {"moyen": PaymentMethod.CC, "montant": 200},
        ],
    )
    part_en_jetons = vente.articles.get(payment_method=PaymentMethod.LOCAL_GIFT)
    part_en_carte = vente.articles.get(payment_method=PaymentMethod.CC)
    return SimpleNamespace(part_en_jetons=part_en_jetons, part_en_carte=part_en_carte)


# --------------------------------------------------------------------------
# Ligne hors Stripe : le champ « Remboursé par »
# / Non-Stripe line: the "Refunded by" field
# --------------------------------------------------------------------------


def test_avoir_admin_rembourse_par_especes_un_seul_reglement(lieu):
    """
    Fiche test 18. Deux billets à 10 € (TVA 5,5 %) vendus dans l'admin, payés par CB
    (`CC`). L'admin émet un avoir et choisit « Remboursé par : espèces » (`CA`), un
    moyen différent du moyen d'origine : il est accepté.
    - L'article d'avoir : même tarif vendu, prix unitaire 1000, quantité −2, TVA 5,5 %,
      total catalogue −2000, rien d'offert, net −2000 (HT −1896, TVA −104), lié à la
      ligne d'origine (`credit_note_for`), à la réservation, avec l'uuid d'origine dans
      `metadata`.
    - La vente AVOIR : origine ADMIN, réglée, liée à la vente d'origine, même client.
    - UN règlement : espèces −2000, sans référence externe.
    - Ordre : à l'encaissement, la ligne d'avoir est encore CREATED ; elle passe
      CREDIT_NOTE ensuite.
    / Test 18. Two admin card tickets, refunded in cash: one AVOIR sale linked to the
    original one, a mirrored item (qty −2, same unit price and VAT), ONE cash payment of
    −2000; the line turns CREDIT_NOTE only after the settlement.
    """
    vente_admin = vendre_et_relire(
        lieu,
        prix="10.00",
        quantite=2,
        moyen_de_paiement=PaymentMethod.CC,
        taux_tva="5.50",
    )
    ligne_d_origine = vente_admin.ligne
    vente_d_origine = Vente.objects.get(pk=ligne_d_origine.vente_id)
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_ecran = ouvrir_l_ecran_de_l_avoir(client_de_l_admin, ligne_d_origine)
    assert "moyen_rembourse" in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)

    with statuts_des_articles_a_l_encaissement() as statuts_releves:
        reponse_de_l_action = valider_l_ecran_de_l_avoir(
            client_de_l_admin, ligne_d_origine, moyen_rembourse=PaymentMethod.CASH
        )

    assert reponse_de_l_action.status_code == 302

    avoir = l_avoir_de_la_ligne(ligne_d_origine)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.pricesold_id == ligne_d_origine.pricesold_id
    assert avoir.amount == 1000
    assert avoir.qty == Decimal("-2")
    assert avoir.vat == Decimal("5.50")
    assert avoir.total_catalogue == -2000
    assert avoir.part_offerte == 0
    assert avoir.total_ttc == -2000
    assert avoir.total_ht == -1896
    assert avoir.total_tva == -104
    assert avoir.reservation_id == ligne_d_origine.reservation_id
    assert avoir.hors_chiffre_affaires == ligne_d_origine.hors_chiffre_affaires
    assert avoir.metadata["original_lignearticle_uuid"] == str(ligne_d_origine.uuid)

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
    )
    assert vente_d_avoir.articles.count() == 1
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.CASH, -2000)
    ]
    assert vente_d_avoir.reglements.get().reference_externe == ""

    # Un seul encaissement pendant l'action : celui de l'avoir, ligne encore CREATED.
    # / One settlement during the action: the credit note's, line still CREATED.
    assert statuts_releves == [[LigneArticle.CREATED]]

    verifier_egalites(vente_d_avoir)


def test_avoir_admin_ecran_pre_rempli_avec_le_moyen_d_origine(lieu):
    """
    L'écran d'une ligne hors Stripe propose « Remboursé par » avec quatre moyens :
    espèces, CB, chèque, virement.
    - Ligne vendue dans l'admin par CB (`CC`, dans la liste) : le champ est pré-rempli
      avec CB.
    - Ligne de caisse payée en monnaie locale (`LE`, hors liste) : le champ est vide.
    Ouvrir l'écran n'écrit rien.
    / A non-Stripe line's screen offers four "Refunded by" methods; pre-filled with the
    original method when it is in the list (CC), empty otherwise (LE). Opening writes
    nothing.
    """
    vente_admin_par_carte = vendre_et_relire(
        lieu, prix="10.00", quantite=1, moyen_de_paiement=PaymentMethod.CC
    )
    ligne_payee_en_monnaie_locale = (
        vendre_a_la_caisse_un_article_paye_en_monnaie_locale()
    )
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    ecran_de_la_ligne_par_carte = ouvrir_l_ecran_de_l_avoir(
        client_de_l_admin, vente_admin_par_carte.ligne
    )
    champs_de_l_ecran = champs_du_formulaire_de_l_ecran(ecran_de_la_ligne_par_carte)
    assert "moyen_rembourse" in champs_de_l_ecran
    moyens_proposes = []
    for valeur, _libelle in champs_de_l_ecran["moyen_rembourse"].choices:
        if valeur:
            moyens_proposes.append(valeur)
    assert sorted(moyens_proposes) == sorted(MOYENS_DU_CHAMP_REMBOURSE_PAR)
    assert valeur_pre_remplie_du_moyen(ecran_de_la_ligne_par_carte) == PaymentMethod.CC

    ecran_de_la_ligne_en_monnaie_locale = ouvrir_l_ecran_de_l_avoir(
        client_de_l_admin, ligne_payee_en_monnaie_locale
    )
    assert "moyen_rembourse" in champs_du_formulaire_de_l_ecran(
        ecran_de_la_ligne_en_monnaie_locale
    )
    assert valeur_pre_remplie_du_moyen(ecran_de_la_ligne_en_monnaie_locale) in (
        None,
        "",
    )

    # Ouvrir l'écran n'écrit aucun avoir.
    # / Opening the screen writes no credit note.
    rien_n_est_ecrit_pour_la_ligne(vente_admin_par_carte.ligne)
    rien_n_est_ecrit_pour_la_ligne(ligne_payee_en_monnaie_locale)


def test_avoir_admin_sans_moyen_refuse(lieu):
    """
    Ligne de caisse payée en monnaie locale (`LE`) : le champ « Remboursé par » est vide
    et obligatoire. L'admin valide sans choisir : l'écran revient (200), aucun avoir,
    aucune vente AVOIR, aucun règlement ; la ligne reste VALID.
    / LE line: the "Refunded by" field is empty and required. Confirming without a
    method writes nothing; the screen comes back.
    """
    ligne_payee_en_monnaie_locale = (
        vendre_a_la_caisse_un_article_paye_en_monnaie_locale()
    )
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_action = valider_l_ecran_de_l_avoir(
        client_de_l_admin, ligne_payee_en_monnaie_locale, moyen_rembourse=""
    )

    assert reponse_de_l_action.status_code == 200
    rien_n_est_ecrit_pour_la_ligne(ligne_payee_en_monnaie_locale)


# --------------------------------------------------------------------------
# Ligne payée par Stripe
# / Stripe-paid line
# --------------------------------------------------------------------------


def test_avoir_admin_ligne_stripe_n_appelle_pas_stripe_et_previent_l_admin(lieu):
    """
    Fiche test 18b. Un billet à 10 € payé en ligne par Stripe. L'écran d'avoir n'a pas
    de champ « Remboursé par » et prévient : « Remboursez cette somme depuis votre
    tableau de bord Stripe. ». L'admin valide.
    - `stripe.Refund.create` n'est JAMAIS appelé.
    - La vente AVOIR, liée à la vente du paiement, même client : UN règlement −1000 au
      moyen Stripe d'origine (`Paiement_stripe.moyen`), relié au paiement d'origine
      (traçabilité), sans référence externe.
    - Le message reste pour l'admin après l'action.
    / Test 18b. Stripe-paid ticket: no "Refunded by" field, a warning to refund from the
    Stripe dashboard, no Stripe call, ONE payment of −1000 at the original Stripe method,
    linked to the original payment, with an empty external reference; the message is
    kept after the action.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=1)
    ligne_d_origine = LigneArticle.objects.get(paiement_stripe=achat.paiement)
    vente_d_origine = Vente.objects.get(pk=ligne_d_origine.vente_id)
    achat.paiement.refresh_from_db()
    moyen_stripe_d_origine = achat.paiement.moyen
    assert moyen_stripe_d_origine, "Le paiement Stripe d'origine n'a pas de moyen."
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_ecran = ouvrir_l_ecran_de_l_avoir(client_de_l_admin, ligne_d_origine)
    assert "moyen_rembourse" not in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)
    assert MESSAGE_REMBOURSEMENT_STRIPE_A_LA_MAIN in reponse_de_l_ecran.content.decode()

    reponse_de_l_action = valider_l_ecran_de_l_avoir(client_de_l_admin, ligne_d_origine)

    assert reponse_de_l_action.status_code == 302
    assert lieu.remboursement_stripe.call_count == 0
    assert MESSAGE_REMBOURSEMENT_STRIPE_A_LA_MAIN in textes_des_messages_de_l_admin(
        reponse_de_l_action
    )

    avoir = l_avoir_de_la_ligne(ligne_d_origine)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.qty == Decimal("-1")
    assert avoir.amount == 1000
    assert avoir.paiement_stripe_id == achat.paiement.pk

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (moyen_stripe_d_origine, -1000)
    ]
    reglement_de_l_avoir = vente_d_avoir.reglements.get()
    assert reglement_de_l_avoir.reference_externe == ""
    assert reglement_de_l_avoir.paiement_stripe_id == achat.paiement.pk
    verifier_egalites(vente_d_avoir)


# --------------------------------------------------------------------------
# Article entièrement offert
# / Fully offered item
# --------------------------------------------------------------------------


def test_avoir_billet_entierement_offert_un_seul_reglement_free(lieu):
    """
    Fiche test 18c. Un billet à 15 € « Offert » vendu dans l'admin (D32 : écrit au prix,
    part offerte = total). L'écran d'avoir n'a PAS de champ « Remboursé par » : il n'y a
    pas d'argent à rendre. L'admin valide.
    - L'article d'avoir : prix unitaire 1500, quantité −1, catalogue −1500, offert
      −1500, net 0, source OFFRIR.
    - UN seul règlement : FREE −1500 (la trace de l'offert annulé), aucun règlement
      d'argent.
    / Test 18c. An admin "offered" 15 € ticket: no "Refunded by" field; the credit note
    has catalogue −1500, offered −1500, net 0, and ONE FREE payment of −1500.
    """
    vente_admin_offerte = vendre_et_relire(
        lieu, prix="15.00", quantite=1, moyen_de_paiement=PaymentMethod.FREE
    )
    ligne_d_origine = vente_admin_offerte.ligne
    vente_d_origine = Vente.objects.get(pk=ligne_d_origine.vente_id)
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_ecran = ouvrir_l_ecran_de_l_avoir(client_de_l_admin, ligne_d_origine)
    assert "moyen_rembourse" not in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)

    reponse_de_l_action = valider_l_ecran_de_l_avoir(client_de_l_admin, ligne_d_origine)

    assert reponse_de_l_action.status_code == 302
    avoir = l_avoir_de_la_ligne(ligne_d_origine)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.amount == 1500
    assert avoir.qty == Decimal("-1")
    assert avoir.total_catalogue == -1500
    assert avoir.part_offerte == -1500
    assert avoir.total_ttc == 0
    assert avoir.source_offert == LigneArticle.SourceOffert.OFFRIR

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.FREE, -1500)
    ]
    verifier_egalites(vente_d_avoir)


def test_avoir_part_en_jetons_de_la_cascade_un_seul_reglement_free(lieu):
    """
    Fiche test 19, en parts. Une bière à 5 € payée 3 € en jetons cadeau et 2 € par CB,
    écrite en deux parts par la caisse en cascade. L'admin émet un avoir sur la part
    « jetons » (entièrement offerte, source JETONS) : pas de champ « Remboursé par ».
    - L'article d'avoir : catalogue −300, offert −300, net 0, source JETONS.
    - UN seul règlement : FREE −300. Aucun jeton n'est recrédité (hors chantier), donc
      pas de règlement LG.
    - La vente AVOIR est liée à la vente de caisse ; son client est vide, comme le
      sien.
    / Test 19, in parts: the credit note of the "tokens" part has catalogue −300,
    offered −300, net 0, and ONE FREE payment of −300; no "Refunded by" field.
    """
    biere_en_deux_parts = vendre_a_la_caisse_une_biere_en_deux_parts()
    part_en_jetons = biere_en_deux_parts.part_en_jetons
    vente_d_origine = Vente.objects.get(pk=part_en_jetons.vente_id)
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_ecran = ouvrir_l_ecran_de_l_avoir(client_de_l_admin, part_en_jetons)
    assert "moyen_rembourse" not in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)

    reponse_de_l_action = valider_l_ecran_de_l_avoir(client_de_l_admin, part_en_jetons)

    assert reponse_de_l_action.status_code == 302
    avoir = l_avoir_de_la_ligne(part_en_jetons)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.amount == 500
    assert avoir.qty == Decimal("-0.6")
    assert avoir.total_catalogue == -300
    assert avoir.part_offerte == -300
    assert avoir.total_ttc == 0
    assert avoir.source_offert == LigneArticle.SourceOffert.JETONS

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=None,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.FREE, -300)
    ]
    verifier_egalites(vente_d_avoir)


def test_avoir_ligne_ancienne_offerte_sans_champ_rembourse_par(lieu):
    """
    Une ligne écrite avant le chantier : un billet à 15 € au moyen historique « offert »
    (`FREE`), sans vente, ses montants entiers à 0. Elle est entièrement offerte par son
    moyen (même règle que le service) : l'écran n'a PAS de champ « Remboursé par ».
    L'avoir : catalogue −1500, offert −1500, net 0, et UN seul règlement FREE −1500
    (posé par la règle « offert » du service, jamais deux fois). Vente AVOIR sans vente
    liée.
    / A pre-chantier "offered" (FREE) line: fully offered by its method, no "Refunded
    by" field; the credit note has ONE FREE payment of −1500, never two.
    """
    tarif_vendu = creer_tarif_vendu(nom="Ancien billet offert", prix_en_euros="15.00")
    # ÉTAT DE DÉPART : une ligne d'avant le chantier, sans vente. `create()` direct :
    # c'est ainsi qu'elles étaient écrites (tests/PIEGES.md 12.17).
    # / STARTING STATE: a pre-chantier line, without sale, written by create().
    ligne_offerte_d_avant_le_chantier = LigneArticle.objects.create(
        pricesold=tarif_vendu,
        qty=1,
        amount=1500,
        vat=Decimal("20"),
        payment_method=PaymentMethod.FREE,
        sale_origin=SaleOrigin.ADMIN,
        status=LigneArticle.VALID,
    )
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_ecran = ouvrir_l_ecran_de_l_avoir(
        client_de_l_admin, ligne_offerte_d_avant_le_chantier
    )
    assert "moyen_rembourse" not in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)

    reponse_de_l_action = valider_l_ecran_de_l_avoir(
        client_de_l_admin, ligne_offerte_d_avant_le_chantier
    )

    assert reponse_de_l_action.status_code == 302
    avoir = l_avoir_de_la_ligne(ligne_offerte_d_avant_le_chantier)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.total_catalogue == -1500
    assert avoir.part_offerte == -1500
    assert avoir.total_ttc == 0

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=None,
        client_attendu=None,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.FREE, -1500)
    ]
    verifier_egalites(vente_d_avoir)


def test_avoir_part_arrondie_rend_exactement_le_total_d_origine(lieu):
    """
    Un article à 10 € payé en deux parts : 6,66 € en espèces (quantité 0,666666) et
    3,34 € par CB (quantité 0,333334, total catalogue IMPOSÉ à 334). Prix × quantité ne
    redonne pas le total de la part CB (1000 × 0,333334 = 333,334 → 333).
    L'avoir de la part CB, rendue entière, rend EXACTEMENT son total d'origine : −334,
    pas −333. UN règlement CB −334.
    / A part whose price × quantity is not exact: its full credit note mirrors the
    original total exactly (−334), not a recomputed one (−333).
    """
    tarif_vendu = creer_tarif_vendu(nom="Article coupé", prix_en_euros="10.00")
    vente_d_origine = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": tarif_vendu,
                "quantite": Decimal("0.666666"),
                "prix_unitaire": 1000,
                "taux_tva": Decimal("20"),
                "total_catalogue_impose": 666,
                "payment_method": PaymentMethod.CASH,
                "status": LigneArticle.VALID,
            },
            {
                "pricesold": tarif_vendu,
                "quantite": Decimal("0.333334"),
                "prix_unitaire": 1000,
                "taux_tva": Decimal("20"),
                "total_catalogue_impose": 334,
                "payment_method": PaymentMethod.CC,
                "status": LigneArticle.VALID,
            },
        ],
        reglements=[
            {"moyen": PaymentMethod.CASH, "montant": 666},
            {"moyen": PaymentMethod.CC, "montant": 334},
        ],
    )
    part_par_carte = vente_d_origine.articles.get(payment_method=PaymentMethod.CC)
    assert part_par_carte.total_catalogue == 334
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_action = valider_l_ecran_de_l_avoir(
        client_de_l_admin, part_par_carte, moyen_rembourse=PaymentMethod.CC
    )

    assert reponse_de_l_action.status_code == 302
    avoir = l_avoir_de_la_ligne(part_par_carte)
    assert avoir.qty == Decimal("-0.333334")
    assert avoir.total_catalogue == -334
    assert avoir.total_ttc == -334

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=None,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.CC, -334)
    ]
    verifier_egalites(vente_d_avoir)


# --------------------------------------------------------------------------
# La fonction du service
# / The service function
# --------------------------------------------------------------------------


def test_avoir_partiel_d_un_article_offert_refuse(lieu):
    """
    Un article vendu en quantité 2 (2 × 10 €) avec 10 € offerts. Rendre UNE seule unité
    de cet article est refusé par `ajouter_l_article_d_avoir` (ValueError, message
    « rembourser l'article entier ») : le projet ne fait aucun prorata d'offert. Aucun
    article n'est ajouté à la vente d'avoir.
    / A qty-2 item with 10 € offered: a partial credit note (qty 1) is refused by the
    service ("refund the whole item"); no item is added.
    """
    tarif_vendu = creer_tarif_vendu(nom="Entrée", prix_en_euros="10.00")
    vente_d_origine = fabriquer_vente_encaissee(
        origine=SaleOrigin.ADMIN,
        articles=[
            {
                "pricesold": tarif_vendu,
                "quantite": Decimal("2"),
                "prix_unitaire": 1000,
                "taux_tva": Decimal("20"),
                "part_offerte": 1000,
                "source_offert": LigneArticle.SourceOffert.OFFRIR,
                "payment_method": PaymentMethod.CASH,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[
            {"moyen": PaymentMethod.CASH, "montant": 1000},
            {"moyen": PaymentMethod.FREE, "montant": 1000},
        ],
    )
    ligne_d_origine = vente_d_origine.articles.get()
    vente_d_avoir = services_vente.ouvrir_vente(
        origine=SaleOrigin.ADMIN,
        nature=Vente.Nature.AVOIR,
        vente_liee=vente_d_origine,
    )

    with pytest.raises(ValueError, match="rembourser l'article entier"):
        services_vente.ajouter_l_article_d_avoir(
            vente_d_avoir, ligne_d_origine, Decimal("1")
        )

    assert not LigneArticle.objects.filter(vente=vente_d_avoir).exists()


# --------------------------------------------------------------------------
# Ligne écrite avant le chantier, et atomicité
# / Line written before the chantier, and atomicity
# --------------------------------------------------------------------------


def test_avoir_ligne_sans_vente_ecrit_une_vente_sans_vente_liee(lieu):
    """
    Une ligne écrite avant le chantier : 10 € en espèces, sans vente (`vente` vide), ses
    montants entiers à 0. L'écran pré-remplit « espèces » ; l'admin valide.
    La vente AVOIR est écrite quand même : réglée, SANS vente liée, sans client.
    L'article : prix unitaire 1000, quantité −1, catalogue −1000, net −1000 (calculés
    par la formule, pas recopiés). UN règlement : espèces −1000.
    / A pre-chantier line without sale: the AVOIR sale is written with no linked sale
    and no client; the item is computed by the formula; one cash payment of −1000.
    """
    tarif_vendu = creer_tarif_vendu(nom="Ancienne vente", prix_en_euros="10.00")
    # ÉTAT DE DÉPART : une ligne d'avant le chantier, sans vente. `create()` direct :
    # c'est ainsi qu'elles étaient écrites (tests/PIEGES.md 12.17).
    # / STARTING STATE: a pre-chantier line, without sale, written by create().
    ligne_d_avant_le_chantier = LigneArticle.objects.create(
        pricesold=tarif_vendu,
        qty=1,
        amount=1000,
        vat=Decimal("20"),
        payment_method=PaymentMethod.CASH,
        sale_origin=SaleOrigin.ADMIN,
        status=LigneArticle.VALID,
    )
    assert ligne_d_avant_le_chantier.vente_id is None
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_ecran = ouvrir_l_ecran_de_l_avoir(
        client_de_l_admin, ligne_d_avant_le_chantier
    )
    assert "moyen_rembourse" in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)
    assert valeur_pre_remplie_du_moyen(reponse_de_l_ecran) == PaymentMethod.CASH

    reponse_de_l_action = valider_l_ecran_de_l_avoir(
        client_de_l_admin, ligne_d_avant_le_chantier, moyen_rembourse=PaymentMethod.CASH
    )

    assert reponse_de_l_action.status_code == 302
    avoir = l_avoir_de_la_ligne(ligne_d_avant_le_chantier)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.amount == 1000
    assert avoir.qty == Decimal("-1")
    assert avoir.total_catalogue == -1000
    assert avoir.total_ttc == -1000

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=None,
        client_attendu=None,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.CASH, -1000)
    ]
    verifier_egalites(vente_d_avoir)


def test_avoir_echec_d_encaissement_rien_n_est_ecrit(lieu):
    """
    Deux billets à 10 € vendus dans l'admin par CB. L'admin émet un avoir remboursé en
    espèces, mais l'encaissement de l'avoir échoue (simulé). Tout ou rien : aucune ligne
    d'avoir, aucune vente AVOIR, aucun règlement négatif ; la ligne reste VALID.
    Peu importe que la vue rende une erreur ou un message : rien n'est écrit.
    / The credit note's settlement fails (faked): nothing is written, whatever the view
    returns.
    """
    vente_admin = vendre_et_relire(
        lieu, prix="10.00", quantite=2, moyen_de_paiement=PaymentMethod.CC
    )
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    # Une exception dans la vue devient une réponse 500, au lieu de sortir du test.
    # / An exception in the view becomes a 500 response instead of leaving the test.
    client_de_l_admin.raise_request_exception = False

    with encaissement_qui_echoue():
        valider_l_ecran_de_l_avoir(
            client_de_l_admin, vente_admin.ligne, moyen_rembourse=PaymentMethod.CASH
        )

    rien_n_est_ecrit_pour_la_ligne(vente_admin.ligne)


def test_avoir_vente_d_origine_pas_reglee_refuse(lieu):
    """
    Une ligne VALID dont la vente d'origine existe mais n'est pas encore réglée (EN
    ATTENTE) : l'avoir est refusé. Aucune ligne d'avoir, aucune vente AVOIR, aucun
    règlement ; un message prévient l'admin.
    / A line whose original sale exists but is not settled: the credit note is refused,
    nothing is written, a message tells the admin.
    """
    tarif_vendu = creer_tarif_vendu(nom="Vente en attente", prix_en_euros="10.00")
    # ÉTAT DE DÉPART : une vente ouverte, avec son article, jamais encaissée.
    # / STARTING STATE: an open sale with its item, never settled.
    vente_en_attente = services_vente.ouvrir_vente(
        origine=SaleOrigin.ADMIN, nature=Vente.Nature.VENTE
    )
    ligne_d_une_vente_en_attente = services_vente.ajouter_article(
        vente_en_attente,
        pricesold=tarif_vendu,
        quantite=Decimal("1"),
        prix_unitaire=1000,
        taux_tva=Decimal("20"),
        payment_method=PaymentMethod.CASH,
        status=LigneArticle.VALID,
    )
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_action = valider_l_ecran_de_l_avoir(
        client_de_l_admin,
        ligne_d_une_vente_en_attente,
        moyen_rembourse=PaymentMethod.CASH,
    )

    assert reponse_de_l_action.status_code == 302
    assert MESSAGE_VENTE_D_ORIGINE_PAS_REGLEE in textes_des_messages_de_l_admin(
        reponse_de_l_action
    )
    rien_n_est_ecrit_pour_la_ligne(ligne_d_une_vente_en_attente)
