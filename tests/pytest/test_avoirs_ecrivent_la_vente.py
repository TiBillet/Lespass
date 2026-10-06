"""
Tests des AVOIRS émis dans l'admin : chaque avoir est une `Vente` de nature AVOIR,
écrite par le service de vente, liée à la vente d'origine, et encaissée.
/ Credit notes issued in the admin: every credit note is an AVOIR `Vente`, written by
the sale service, linked to the original sale, and settled.

LOCALISATION : tests/pytest/test_avoirs_ecrivent_la_vente.py

LA RÈGLE TESTÉE
L'admin ouvre « Avoir sur un article » depuis la fiche de la vente et choisit une ligne.
Un écran s'ouvre (GET) ; l'admin le valide (POST) avec toute la quantité de la ligne.
L'avoir est alors :
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
- ligne payée en jetons cadeau (LG, vente ordinaire à TVA 0, D8 bis) : pas de champ,
  un seul règlement « jetons » (LG) négatif, avec la monnaie et la carte de la ligne,
  aucun recrédit de la carte ;
- ligne payée par Stripe : pas de champ, l'écran prévient « Remboursez cette somme
  depuis votre tableau de bord Stripe. », aucun appel à Stripe, règlement négatif au
  moyen Stripe d'origine, sans référence externe.
/ The admin opens the "credit note" screen (GET) and confirms it (POST): one AVOIR sale,
linked, one item mirrored with a negative quantity, one money payment at the chosen
"Refunded by" method, one FREE payment for the offered part, settled, then CREDIT_NOTE.

CONTRAT DE L'ÉCRAN (ce que ces tests supposent de l'interface)
- URL : `/admin/BaseBillet/vente/<uuid de la vente>/avoir_sur_un_article/?ligne=<pk>`,
  GET = écran (200), POST avec `quantite` = toute la quantité de la ligne = action
  (302 si l'avoir est émis) ;
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

LE REMBOURSEMENT STRIPE (dernière partie du fichier)
Un remboursement Stripe (`partial_refund_payment`, total ou partiel) écrit, lui aussi,
UNE vente AVOIR : origine LESPASS, liée à la vente du paiement, client = celui de cette
vente. Un article par ligne remboursée (`ajouter_l_article_d_avoir`), écrit AVANT l'appel
à Stripe : un refus du service n'appelle jamais Stripe. Puis UN règlement Stripe négatif,
au montant RENVOYÉ par Stripe (`refund.amount`, jamais calculé), avec l'identifiant du
remboursement (`refund.id`) en référence externe. Si ce montant diffère des articles, un
article « Écart d'encaissement » (comme à l'encaissement en ligne) et une alerte ERROR.
Encaissée, PUIS les lignes passent REFUNDED. Tout ou rien.
/ A Stripe refund writes ONE AVOIR sale (LESPASS), items written BEFORE the Stripe call,
one negative Stripe payment of the amount Stripe returns, the refund id as external
reference, a gap item when amounts differ; settled, then REFUNDED. All or nothing.

LES ANNULATIONS (fin du fichier)
- L'ADMIN annule des réservations ou des billets (actions de liste). Un écran s'ouvre
  d'abord. Le champ « Remboursé par » n'y est que si une ligne hors Stripe de la
  sélection a de l'argent à rendre ; il est alors obligatoire, et un seul moyen vaut pour
  toute la sélection. Chaque ligne hors Stripe reçoit son avoir, écrit comme celui du
  bouton « Avoir » : une vente AVOIR encaissée, origine ADMIN. Un billet seul = un avoir
  d'une unité, même d'une ligne entièrement offerte.
- L'UTILISATEUR annule depuis « Mon compte » une réservation, un billet ou un booking payé
  hors Stripe (D31) : AUCUN avoir, aucune vente ; seuls la réservation, le billet ou le
  booking passent annulés.
/ The ADMIN cancels through a screen ("Refunded by" only when money is owed); each
non-Stripe line gets a settled AVOIR sale. The USER cancelling a non-Stripe purchase
(D31) gets no credit note and no sale: only the statuses change.

CONTRAT DE L'ÉCRAN D'ANNULATION (comme la confirmation de suppression de Django)
- 1er POST sur la liste (`action`, `_selected_action`) : l'écran (200), contexte `form` ;
- 2e POST : les mêmes données, plus `post=yes` et `moyen_rembourse` s'il est choisi ;
  l'annulation est faite (302) ; formulaire refusé : l'écran revient (200).
/ First POST = the screen (200, `form` context); second POST adds `post=yes` and
`moyen_rembourse`; refused form = screen again (200).

L'ANNULATION D'ADHÉSION PAR L'ADMIN (D30, fin du fichier)
L'admin annule une adhésion depuis sa fiche, bouton « Annuler avec avoir ». UN SEUL
avoir, sur le DERNIER paiement de l'adhésion (sa ligne VALID / PAID la plus récente, par
date) : les renouvellements passés ne sont jamais touchés, et si ce dernier paiement a
déjà un avoir ou un remboursement, aucun avoir n'est écrit (pas de remontée). L'avoir
est écrit comme celui du bouton « Avoir » ; l'annulation et l'avoir : tout ou rien.
/ ONE credit note, on the latest payment only; none if that payment already has one;
written like the "Credit note" button; cancellation and credit note: all or nothing.

CONTRAT DU FORMULAIRE D'ANNULATION D'ADHÉSION (partiel HTMX de la vue DRF)
- GET `/memberships/<pk>/cancel/` : le formulaire (200). Ligne hors Stripe, pas
  entièrement offerte : une liste `<select name="moyen_rembourse">` (espèces, CB,
  chèque, virement), l'`<option>` du moyen d'origine marquée `selected` s'il est dans la
  liste. Ligne payée par Stripe : pas de liste, la phrase « Remboursez cette somme
  depuis votre tableau de bord Stripe. » ;
- POST `with_credit_note=1` (+ `moyen_rembourse`) : annulation faite, 204 avec
  `HX-Redirect` ; moyen manquant alors qu'il est demandé : le formulaire revient (200),
  rien n'est annulé.
/ GET = the form, with a `moyen_rembourse` select for a non-Stripe line (pre-selected
original method) or the Stripe sentence; POST = 204, or the form again (200) when the
method is missing.

DOUBLE DEMANDE ET NOUVEL ESSAI
- Deux demandes d'avoir pour la même ligne (double clic) : la seconde est refusée. La
  quantité déjà rendue (avoirs et remboursements Stripe) est relue sous verrou, dans la
  fonction commune comme dans le remboursement Stripe, avant toute écriture et avant
  tout appel à Stripe.
- Le remboursement Stripe porte une clé d'idempotence `remboursement-{paiement}-{n}`,
  `n` = nombre de règlements négatifs déjà écrits pour ce paiement. Un nouvel essai après
  un échec (rien d'écrit) envoie la MÊME clé : Stripe rend le même remboursement. Le
  remboursement suivant, une fois le premier écrit, a une clé nouvelle.
/ A second credit note request for the same line is refused (credited quantity read
again under lock). The Stripe refund carries an idempotency key: same key on a retry,
a new key for the next refund.

DEMANDES SIMULTANÉES (VERROUS)
- Deux demandes d'annulation du même billet (deux onglets, le client et l'admin) : la
  seconde relit le billet sous verrou ; il est déjà annulé, elle est refusée avant
  Stripe. De même pour deux annulations de toute la réservation.
- Le `n` de la clé d'idempotence est compté sous le verrou du paiement Stripe : deux
  remboursements du même paiement passent l'un après l'autre, le second lit `n` + 1.
  Une seule connexion ne peut pas faire attendre une autre demande : le test relève les
  requêtes SQL et vérifie que le paiement est verrouillé AVANT le comptage.
/ Two cancellations of the same ticket: the second reads the ticket again under lock
and is refused. `n` is counted under the payment's lock (checked on the SQL queries).

DEUX LIGNES DU MÊME TARIF VENDU (PANIER, PRIX LIBRE)
Deux billets à prix libre saisis au même montant font deux lignes du même tarif vendu.
L'annulation Stripe répartit les billets actifs entre les lignes : une ligne ne reçoit
jamais plus que ce qu'il lui reste à rendre. Un billet seul est rendu sur une ligne qui
a encore une quantité à rendre.
/ Two lines of the same PriceSold: active tickets are spread between the lines.

ÉCART « REÇU EN MOINS » À L'ENCAISSEMENT
Stripe a encaissé moins que les articles. Le remboursement ne demande jamais à Stripe
plus que ce qu'il détient encore pour ce paiement (`montant_encaisse` moins les
remboursements déjà écrits) ; la différence avec les articles devient l'article d'écart.
/ The refund never asks Stripe more than it still holds for the payment.

L'ANCIEN LABOUTIK (V1)
Aucun avoir fait dans l'admin (bouton « Avoir », annulations admin, annulation
d'adhésion, origine ADMIN) n'est envoyé à LaBoutik V1 : les ventes admin n'y partent
pas non plus. Un remboursement Stripe (origine LESPASS, statut REFUNDED) y part toujours,
et seulement APRÈS la validation de la transaction (`transaction.on_commit`).
/ No admin credit note is sent to LaBoutik V1; a Stripe refund still is, after commit.

LES BILLETS VENDUS À LA CAISSE
La caisse écrit sa ligne et ses billets sur deux tarifs vendus (`PriceSold`) différents
du même tarif (`Price`) (laboutik/views.py). L'écran d'annulation et l'annulation d'un
billet retrouvent la ligne par le tarif, comme l'annulation d'une réservation.
/ The register writes its line and its tickets on two PriceSold of the same Price: the
cancel screen and the single-ticket cancellation match lines by Price.

LES LIGNES PAYÉES EN POINTS OU EN TEMPS (fin du fichier)
Une ligne d'une vente qui n'est pas en euros (vente en points de la caisse, recharge
offerte en points de l'API v2), ou une ligne au moyen « points ou temps » (NM), ne reçoit
jamais d'avoir : un avoir est une vente en euros, il rendrait de l'argent pour des
points. Le refus est dans la fonction commune `ajouter_l_article_d_avoir` ; le bouton
« Avoir » ne s'ouvre pas ; le formulaire d'annulation d'une adhésion payée en points ne
propose que « Annuler sans avoir » et le dit dans une phrase visible.
/ A line of a non-euro sale, or with the NM method, never gets a credit note: refused by
the shared function, the button does not open, the membership form says so.

LE COÛT D'ACHAT DE L'AVOIR (fin du fichier)
L'avoir reprend en négatif le coût figé de la ligne d'origine, au prorata de la quantité
rendue, arrondi demi-haut ; une ligne sans coût donne un avoir sans coût.
/ The credit note takes the original line's frozen cost back, negative, prorated and
rounded half up; no cost gives no cost.

CODE PARCOURU / CODE EXERCISED
- Administration/admin_tenant.py — VenteAdmin.avoir_sur_un_article (écran et action) ;
  ReservationAdmin.action_cancel_refund_reservations, TicketAdmin.action_cancel_refund_selected ;
- BaseBillet/views.py — MembershipMVT.cancel (annulation d'adhésion, et son gabarit
  Administration/templates/admin/membership/partials/cancel_form.html) ;
- BaseBillet/services_vente.py — ecrire_la_vente_d_avoir_d_une_ligne,
  ajouter_l_article_d_avoir, ouvrir_vente, ajouter_reglement, encaisser_vente ;
- BaseBillet/models.py — Reservation.cancel_and_refund_resa, cancel_and_refund_ticket ;
  booking/models.py — Booking.cancel_and_refund_booking ;
- PaiementStripe/utils.py — partial_refund_payment (remboursement Stripe), appelé par
  Reservation.cancel_and_refund_ticket / cancel_and_refund_resa et
  Booking.cancel_and_refund_booking.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-D-en-ligne-avoirs.md (§4,
§5 tests 17, 18, 18b, 18c, 19, 20, 21, annexes T7, T8, T9) ; CHANTIER-05-SUIVI.md §4
(D-3, D-3c, D-3z, grandes relectures de la fiche D) et §5 (LaBoutik V1, 2026-10-02) ;
briefs CHANTIER-05-briefs/05-D-3a.md, 05-D-3b.md, 05-D-3c-1.md, 05-D-3c-2.md,
05-D-3z.md et 05-D-4a.md.

Lancer / Run : make test ARGS="tests/pytest/test_avoirs_ecrivent_la_vente.py"
"""

import logging
import uuid
from contextlib import contextmanager
from decimal import Decimal
from html import unescape
from html.parser import HTMLParser
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.utils import translation
from django.utils.html import escape
from django_tenants.utils import tenant_context

from BaseBillet import services_vente
from BaseBillet.models import (
    Configuration,
    LigneArticle,
    Membership,
    Paiement_stripe,
    PaymentMethod,
    PriceSold,
    Product,
    ProductSold,
    Reservation,
    SaleOrigin,
    Ticket,
)
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.services_panier import PanierSession
from BaseBillet.services_vente import (
    MOYENS_DU_CHAMP_REMBOURSE_PAR,
    NOM_ECART_RECU_EN_PLUS,
)
from ApiBillet.serializers import get_or_create_price_sold
from booking.models import Booking
from PaiementStripe.utils import partial_refund_payment
from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    configuration_modifiee,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_ressource_avec_tarif,
    creer_utilisateur,
    identifiant_unique,
    noms_des_taches,
    requete_avec_session,
    taches_celery_enregistrees,
)
from fabriques_vente import (
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from fedow_core.models import Transaction
from laboutik.models import PointDeVente
from laboutik.views import _taux_tva_de_la_ligne_de_caisse
from QrcodeCashless.models import CarteCashless
from test_admin_ecrit_la_vente import (
    creer_l_adhesion_et_relire,
    encaissement_qui_echoue,
    moyens_et_montants_des_reglements,
    statuts_des_articles_a_l_encaissement,
    vendre_et_relire,
)
from test_caracterisation_admin_api import reserver_une_ressource_sans_panier
from test_caracterisation_annulations import (
    acheter_des_billets_payes_par_stripe,
    acheter_une_adhesion_payee_par_stripe,
    annuler_un_billet_depuis_mon_compte,
    annuler_une_reservation_depuis_mon_compte,
    client_de_mon_compte,
    creer_une_adhesion_payee_trois_fois,
    rembourser_comme_stripe,
)
from test_caracterisation_en_ligne import (
    EN_TETE_HTMX,
    arguments_des_taches,
    creer_un_administrateur_du_lieu,
    revenir_de_stripe_billetterie,
)
from test_en_ligne_ecrit_la_vente import (
    articles_d_ecart_de_la_vente,
    payer_le_panier,
    position_de_la_premiere_requete,
    requetes_sql_relevees,
    reserver_des_billets_a_payer,
    verifier_l_article_d_ecart,
)

pytestmark = pytest.mark.django_db

# Le message de l'écran d'une ligne payée par Stripe (msgid français).
# / The screen message for a Stripe-paid line (French msgid).
MESSAGE_REMBOURSEMENT_STRIPE_A_LA_MAIN = (
    "Remboursez cette somme depuis votre tableau de bord Stripe."
)

# Le refus d'un avoir quand la vente d'origine n'est pas réglée (msgid français).
# / The refusal when the original sale is not settled (French msgid).
MESSAGE_VENTE_D_ORIGINE_PAS_REGLEE = (
    "La vente n'est pas réglée : l'avoir est impossible."
)

# Les messages de l'utilisateur qui annule un achat réglé sur place (D31, msgid
# français). Réservation et billet : la vue ajoute déjà « … has been cancelled. »
# devant, le modèle ne rend que la phrase complémentaire. Booking : sa vue n'ajoute
# rien, la phrase est complète.
# / Messages for a user cancelling an on-site purchase (D31, French msgids).
MESSAGE_COMPLEMENTAIRE_REGLE_SUR_PLACE = (
    "Réglé sur place : pour un éventuel remboursement, contactez l'organisateur."
)
MESSAGE_BOOKING_REGLE_SUR_PLACE = (
    "Votre réservation est annulée. Elle a été réglée sur place : pour un éventuel "
    "remboursement, contactez l'organisateur."
)

# La langue des clients de test : `client_connecte` (fabriques_panier.py) envoie
# `Accept-Language: en`. Les textes attendus sont traduits dans cette langue : le test
# reste vrai quand la traduction anglaise d'un msgid arrive.
# / The test clients' language (Accept-Language: en): expected texts are translated in
# it, so the test stays true when an English translation arrives.
LANGUE_DES_CLIENTS_DE_TEST = "en"


def dans_la_langue_du_client(msgid):
    """Le texte que le client de test lit pour ce msgid.
    / The text the test client reads for this msgid."""
    with translation.override(LANGUE_DES_CLIENTS_DE_TEST):
        return translation.gettext(msgid)


def dans_la_langue_active(msgid):
    """Le texte de ce msgid dans la langue active du test (code appelé sans client).
    / The text of this msgid in the test's active language (code called without client)."""
    return translation.gettext(msgid)


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

    `remboursement_stripe` remplace `stripe.Refund.create` : on compte ses appels. Il
    rend un remboursement comme Stripe (`rembourser_comme_stripe`) : un identifiant et
    le montant rendu, en centimes entiers.
    / `remboursement_stripe` replaces `stripe.Refund.create`: its calls are counted. It
    returns a refund like Stripe does: an id and the amount given back, in cents.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule():
            with taches_celery_enregistrees() as taches_demandees:
                with patch(
                    "stripe.Refund.create", side_effect=rembourser_comme_stripe
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
    """L'adresse de l'écran « Avoir sur un article » de la fiche « Vente », pour cette
    ligne. / The "Credit note on one item" screen address, for this line."""
    return f"/admin/BaseBillet/vente/{ligne.vente_id}/avoir_sur_un_article/?ligne={ligne.pk}"


def ouvrir_l_ecran_de_l_avoir(client_de_l_admin, ligne):
    """L'admin choisit la ligne dans « Avoir sur un article » : l'écran s'ouvre (GET).
    / The admin picks the line in "Credit note on one item": the screen opens (GET)."""
    return client_de_l_admin.get(url_de_l_avoir(ligne))


def valider_l_ecran_de_l_avoir(client_de_l_admin, ligne, moyen_rembourse=None):
    """
    L'admin valide l'écran (POST) avec TOUTE la quantité de la ligne (relue en base),
    et le moyen « Remboursé par » choisi s'il y en a un. Sans moyen, le formulaire est
    envoyé sans ce champ.
    / The admin confirms the screen (POST) with the whole line quantity, and the
    chosen "Refunded by" method if any.
    """
    quantite_de_la_ligne = LigneArticle.objects.get(pk=ligne.pk).qty
    donnees_du_formulaire = {"quantite": str(quantite_de_la_ligne)}
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


def verifier_la_vente_d_avoir_encaissee(
    avoir, vente_liee_attendue, client_attendu, origine_attendue=SaleOrigin.ADMIN
):
    """
    Relit la vente de la ligne d'avoir et vérifie la règle commune : nature AVOIR,
    origine attendue (ADMIN pour l'écran d'avoir, LESPASS pour un remboursement Stripe),
    REGLEE, numérotée, liée à la vente d'origine, client attendu.
    / Reads the credit note's sale back: AVOIR, expected origin, settled, numbered,
    linked, client.

    :return: la vente d'avoir relue
    """
    assert avoir.vente_id is not None, "La ligne d'avoir n'a pas de vente."
    vente_d_avoir = Vente.objects.get(pk=avoir.vente_id)
    assert vente_d_avoir.nature == Vente.Nature.AVOIR
    assert vente_d_avoir.origine == origine_attendue
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
    - part « jetons » : quantité 0,6, total catalogue imposé 300, part payée en jetons
      300 (vente ordinaire hors TVA, rien d'offert, D8 bis), taux du produit, moyen
      historique LG ;
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
                "part_en_jetons": 300,
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
    assert (
        dans_la_langue_du_client(MESSAGE_REMBOURSEMENT_STRIPE_A_LA_MAIN)
        in reponse_de_l_ecran.content.decode()
    )

    reponse_de_l_action = valider_l_ecran_de_l_avoir(client_de_l_admin, ligne_d_origine)

    assert reponse_de_l_action.status_code == 302
    assert lieu.remboursement_stripe.call_count == 0
    assert dans_la_langue_du_client(
        MESSAGE_REMBOURSEMENT_STRIPE_A_LA_MAIN
    ) in textes_des_messages_de_l_admin(reponse_de_l_action)

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


def test_avoir_part_en_jetons_de_la_cascade_un_seul_reglement_lg(lieu):
    """
    Fiche test 19, en parts. Une bière à 5 € payée 3 € en jetons cadeau et 2 € par CB,
    écrite en deux parts par la caisse en cascade. L'admin émet un avoir sur la part
    « jetons » (vente ordinaire à TVA 0, D8 bis) : pas d'argent à rendre, donc pas de
    champ « Remboursé par ».
    - L'article d'avoir : catalogue −300, rien d'offert, net −300.
    - UN seul règlement : jetons (LG) −300. Aucun jeton n'est recrédité : la dette du
      lieu revient, les jetons ne reviennent pas.
    - La vente AVOIR est liée à la vente de caisse ; son client est vide, comme le
      sien.
    / Test 19, in parts: the credit note of the "tokens" part has catalogue −300,
    nothing offered, net −300, and ONE LG payment of −300; no "Refunded by" field.
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
    assert avoir.part_offerte == 0
    assert avoir.total_ttc == -300
    assert avoir.source_offert == ""

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=None,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.LOCAL_GIFT, -300)
    ]
    verifier_egalites(vente_d_avoir)


# --------------------------------------------------------------------------
# Part payée en jetons : pas d'argent à rendre, la dette revient (D8 bis)
# / Part paid in tokens: no money to give back, the debt comes back (D8 bis)
# --------------------------------------------------------------------------


def vendre_un_billet_paye_en_jetons():
    """
    ÉTAT DE DÉPART : un billet à 5 € (réservation validée, un billet actif), payé en
    jetons cadeau (`LG`) par une carte, écrit par le service de vente comme une part en
    jetons d'aujourd'hui (D8 bis) : une vente ordinaire, rien d'offert, net 500, part
    payée en jetons 500, au taux que la caisse écrit pour ce produit
    (`_taux_tva_de_la_ligne_de_caisse`), donc TVA 0 ; avec la monnaie des jetons et la
    carte. Règlement : jetons (LG) 500, même monnaie, même carte. La réservation et son
    billet sont posés par `create(status=…)`, sans machine à états (tests/PIEGES.md
    12.17).
    Rend la réservation, la ligne, sa vente, la carte et la monnaie des jetons.
    / STARTING STATE: a 5 € ticket paid in gift tokens (LG) by a card, written by the
    sale service as a D8 bis token part (ordinary sale, net 500, VAT 0), one LG payment.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="5.00")
    produit_vendu, _produit_vendu_cree = ProductSold.objects.get_or_create(
        product=concert.produit, event=concert.evenement
    )
    tarif_vendu = PriceSold.objects.create(
        productsold=produit_vendu, price=concert.tarif, prix=concert.tarif.prix
    )
    reservation = Reservation.objects.create(
        user_commande=acheteur, event=concert.evenement, status=Reservation.VALID
    )
    Ticket.objects.create(
        reservation=reservation, pricesold=tarif_vendu, status=Ticket.NOT_SCANNED
    )

    # `tag_id` et `number` font 8 caractères au plus (tests/PIEGES.md 9.31).
    # / `tag_id` and `number` are 8 characters at most.
    identifiant_de_la_carte = identifiant_unique().upper()
    carte_du_client = CarteCashless.objects.create(
        tag_id=identifiant_de_la_carte,
        number=identifiant_de_la_carte,
        uuid=uuid.uuid4(),
    )
    monnaie_des_jetons = uuid.uuid4()

    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": tarif_vendu,
                "quantite": Decimal("1"),
                "prix_unitaire": 500,
                "taux_tva": _taux_tva_de_la_ligne_de_caisse(
                    concert.produit, PaymentMethod.LOCAL_GIFT
                ),
                "part_en_jetons": 500,
                "payment_method": PaymentMethod.LOCAL_GIFT,
                "asset": monnaie_des_jetons,
                "carte": carte_du_client,
                "reservation": reservation,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[
            {
                "moyen": PaymentMethod.LOCAL_GIFT,
                "montant": 500,
                "asset": monnaie_des_jetons,
                "carte": carte_du_client,
            }
        ],
    )
    return SimpleNamespace(
        reservation=reservation,
        ligne=vente.articles.get(),
        vente=vente,
        carte=carte_du_client,
        monnaie_des_jetons=monnaie_des_jetons,
    )


@pytest.mark.parametrize(
    "geste_de_l_admin", ["bouton_avoir", "annulation_de_la_reservation"]
)
def test_avoir_d_une_part_en_jetons_reglement_lg_negatif_sans_rembourse_par(
    lieu, geste_de_l_admin
):
    """
    Un billet à 5 € payé en jetons cadeau (D8 bis : vente ordinaire, net 500, TVA 0).
    L'admin le rend, par le bouton « Avoir » ou par l'annulation de la réservation.
    Une part payée en jetons n'a PAS d'argent à rendre :
    - l'écran n'a PAS de champ « Remboursé par » ; l'admin valide sans moyen ;
    - l'article d'avoir : quantité −1, catalogue −500, rien d'offert, net −500, part
      en jetons −500, taux de la ligne d'origine, TVA 0,
      moyen historique LG ;
    - UN seul règlement : jetons (LG) −500, avec la monnaie et la carte du règlement
      LG de la vente d'origine ; aucun règlement FREE, aucun règlement d'argent ;
    - la carte n'est PAS recréditée (aucune transaction Fedow) : la dette du lieu
      revient, les jetons ne reviennent pas (tronc §9).
    / A ticket paid in gift tokens, given back by the "Credit note" button or by the
    reservation cancellation: no "Refunded by" field, a mirrored item (net −500, VAT 0),
    ONE LG payment of −500 with the line's currency and card, no FREE payment, and the
    card is not credited back.
    """
    billet_en_jetons = vendre_un_billet_paye_en_jetons()
    ligne_d_origine = billet_en_jetons.ligne
    reservation = billet_en_jetons.reservation
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    if geste_de_l_admin == "bouton_avoir":
        reponse_de_l_ecran = ouvrir_l_ecran_de_l_avoir(
            client_de_l_admin, ligne_d_origine
        )
        assert "moyen_rembourse" not in champs_du_formulaire_de_l_ecran(
            reponse_de_l_ecran
        )
        reponse_de_l_action = valider_l_ecran_de_l_avoir(
            client_de_l_admin, ligne_d_origine
        )
    else:
        reponse_de_l_ecran = lancer_l_action_d_annulation(
            client_de_l_admin,
            URL_DE_LA_LISTE_DES_RESERVATIONS,
            ACTION_ANNULER_LES_RESERVATIONS,
            [reservation],
        )
        assert "moyen_rembourse" not in champs_du_formulaire_de_l_ecran(
            reponse_de_l_ecran
        )
        reponse_de_l_action = confirmer_l_ecran_d_annulation(
            client_de_l_admin,
            URL_DE_LA_LISTE_DES_RESERVATIONS,
            ACTION_ANNULER_LES_RESERVATIONS,
            [reservation],
        )

    assert reponse_de_l_action.status_code == 302
    if geste_de_l_admin == "annulation_de_la_reservation":
        reservation.refresh_from_db()
        assert reservation.status == Reservation.CANCELED

    avoir = l_avoir_de_la_ligne(ligne_d_origine)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.qty == Decimal("-1")
    assert avoir.amount == 500
    assert avoir.total_catalogue == -500
    assert avoir.part_offerte == 0
    assert avoir.total_ttc == -500
    assert avoir.vat == ligne_d_origine.vat
    assert avoir.part_en_jetons == -500
    assert avoir.total_tva == 0
    assert avoir.payment_method == PaymentMethod.LOCAL_GIFT

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=billet_en_jetons.vente,
        client_attendu=billet_en_jetons.vente.client,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.LOCAL_GIFT, -500)
    ]
    reglement_des_jetons = vente_d_avoir.reglements.get()
    assert reglement_des_jetons.asset == billet_en_jetons.monnaie_des_jetons
    assert reglement_des_jetons.carte_id == billet_en_jetons.carte.pk

    # Aucun recrédit de la carte : aucune transaction Fedow ne la touche.
    # / No credit back on the card: no Fedow transaction touches it.
    assert not Transaction.objects.filter(card=billet_en_jetons.carte).exists()
    verifier_egalites(vente_d_avoir)


def test_avoir_ligne_ancienne_offerte_sans_champ_rembourse_par(lieu):
    """
    Une ligne écrite avant le chantier : un billet à 15 € au moyen historique « offert »
    (`FREE`), sans vente, ses montants entiers à 0. Elle est entièrement offerte par son
    moyen (`ligne_sans_argent_a_rendre`) : aucun argent n'est à rendre, donc pas de
    champ « Remboursé par ». L'avoir est écrit par le service (origine ADMIN).
    L'avoir : catalogue −1500, offert −1500, net 0, et UN seul règlement FREE −1500
    (posé par la règle « offert » du service, jamais deux fois). Vente AVOIR sans vente
    liée.
    / A pre-chantier "offered" (FREE) line: fully offered by its method, no "Refunded
    by" field; the credit note has ONE FREE payment of −1500, never two.
    """
    tarif_vendu = creer_tarif_vendu(nom="Ancien billet offert", prix_en_euros="15.00")
    # Une ligne sans vente n'a plus d'écran dans l'admin (l'avoir se fait depuis la
    # fiche « Vente ») : on vérifie la règle de l'écran (`ligne_sans_argent_a_rendre`,
    # pas de champ « Remboursé par ») et l'écriture du service, appelé comme l'écran.
    # / A line without sale has no admin screen: the screen rule and the service.
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
    assert services_vente.ligne_sans_argent_a_rendre(ligne_offerte_d_avant_le_chantier)

    services_vente.ecrire_la_vente_d_avoir_d_une_ligne(
        ligne_offerte_d_avant_le_chantier,
        quantite=ligne_offerte_d_avant_le_chantier.qty,
        moyen_rembourse=None,
        origine=SaleOrigin.ADMIN,
    )

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
    montants entiers à 0. Le moyen d'origine est « espèces » ; l'avoir est écrit par
    le service (origine ADMIN), remboursé en espèces.
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
    # Une ligne sans vente n'a plus d'écran dans l'admin : on vérifie les règles de
    # l'écran (argent à rendre, moyen d'origine pré-rempli) et l'écriture du service.
    # / A line without sale has no admin screen: the screen rules and the service.
    assert not services_vente.ligne_sans_argent_a_rendre(ligne_d_avant_le_chantier)
    assert (
        services_vente.moyen_d_origine_de_la_ligne(ligne_d_avant_le_chantier)
        == PaymentMethod.CASH
    )

    services_vente.ecrire_la_vente_d_avoir_d_une_ligne(
        ligne_d_avant_le_chantier,
        quantite=ligne_d_avant_le_chantier.qty,
        moyen_rembourse=PaymentMethod.CASH,
        origine=SaleOrigin.ADMIN,
    )

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
    assert dans_la_langue_du_client(
        MESSAGE_VENTE_D_ORIGINE_PAS_REGLEE
    ) in textes_des_messages_de_l_admin(reponse_de_l_action)
    rien_n_est_ecrit_pour_la_ligne(ligne_d_une_vente_en_attente)


# --------------------------------------------------------------------------
# Double demande : la quantité déjà rendue est relue sous verrou
# / Double request: the quantity already given back is read again under lock
# --------------------------------------------------------------------------


def test_avoir_deux_fois_la_meme_ligne_refuse_le_second(lieu):
    """
    Deux billets à 10 € vendus dans l'admin par CB. Deux demandes d'avoir arrivent pour
    toute la ligne, comme deux POST d'un double clic : chacune a lu la ligne AVANT que
    l'autre n'écrive. La seconde porte donc une ligne périmée, qui ne voit pas le premier
    avoir.
    - La première demande écrit l'avoir : quantité −2.
    - La seconde est refusée (ValueError) : la fonction commune relit, sous verrou, la
      quantité déjà rendue ; il ne reste rien.
    - Une seule ligne d'avoir, une seule vente AVOIR liée à la vente d'origine.
    Les deux demandes passent par la fonction commune, pas par l'écran : la garde de
    l'écran (« un avoir existe déjà ») arrête deux POST l'un après l'autre, pas deux POST
    simultanés, qu'un test ne sait pas jouer.
    / Two credit note requests for the whole line, the second one holding a stale line:
    the second is refused (the quantity given back is read again under lock); one credit
    note line, one AVOIR sale.
    """
    vente_admin = vendre_et_relire(
        lieu, prix="10.00", quantite=2, moyen_de_paiement=PaymentMethod.CC
    )
    ligne_lue_par_la_premiere_demande = vente_admin.ligne
    ligne_lue_par_la_seconde_demande = LigneArticle.objects.get(pk=vente_admin.ligne.pk)
    vente_d_origine = Vente.objects.get(pk=vente_admin.ligne.vente_id)

    services_vente.ecrire_la_vente_d_avoir_d_une_ligne(
        ligne_lue_par_la_premiere_demande,
        quantite=Decimal("2"),
        moyen_rembourse=PaymentMethod.CASH,
        origine=SaleOrigin.ADMIN,
    )

    with pytest.raises(ValueError):
        services_vente.ecrire_la_vente_d_avoir_d_une_ligne(
            ligne_lue_par_la_seconde_demande,
            quantite=Decimal("2"),
            moyen_rembourse=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )

    assert (
        LigneArticle.objects.filter(credit_note_for=vente_admin.ligne).count() == 1
    ), "La même ligne a reçu deux avoirs."
    assert (
        Vente.objects.filter(
            nature=Vente.Nature.AVOIR, vente_liee=vente_d_origine
        ).count()
        == 1
    ), "Deux ventes AVOIR ont été écrites pour la même ligne."


# --------------------------------------------------------------------------
# Remboursement Stripe : une vente AVOIR au montant renvoyé par Stripe
# / Stripe refund: one AVOIR sale at the amount Stripe returns
# --------------------------------------------------------------------------

# Les journaux où l'alerte d'écart et l'erreur après remboursement peuvent être écrites :
# le service de vente, ou la fonction de remboursement.
# / The loggers that may carry the gap alert and the after-refund error.
JOURNAUX_DU_REMBOURSEMENT_STRIPE = ("BaseBillet.services_vente", "PaiementStripe.utils")


@contextmanager
def remboursement_stripe_simule(montant_rendu_par_stripe=None):
    """
    Remplace `stripe.Refund.create` le temps du bloc. Chaque appel rend un remboursement
    réussi, avec un identifiant unique et le montant rendu : le montant demandé, ou
    `montant_rendu_par_stripe` s'il est donné (frais, arrondi chez Stripe).
    / Replaces `stripe.Refund.create` within the block. Each call returns a successful
    refund with a unique id and the amount given back: the amount asked, or
    `montant_rendu_par_stripe` when given.

    :param montant_rendu_par_stripe: centimes que Stripe annonce rendus, ou None
    :return: un objet avec `appels` (le faux `Refund.create`, pour compter et lire ses
        arguments) et `remboursements_rendus` (les objets rendus, dans l'ordre)
    """
    remboursements_rendus = []

    def rembourser(**arguments_du_remboursement):
        remboursement = rembourser_comme_stripe(**arguments_du_remboursement)
        if montant_rendu_par_stripe is not None:
            remboursement.amount = montant_rendu_par_stripe
        remboursements_rendus.append(remboursement)
        return remboursement

    with patch("stripe.Refund.create", side_effect=rembourser) as appels_a_stripe:
        yield SimpleNamespace(
            appels=appels_a_stripe,
            remboursements_rendus=remboursements_rendus,
        )


def le_remboursement_de_la_ligne(ligne):
    """
    La ligne négative qui rembourse cette ligne payée par Stripe : même paiement Stripe,
    quantité négative, uuid de la ligne d'origine dans `metadata`. Une seule attendue.
    / The negative line that refunds this Stripe-paid line. Exactly one expected.
    """
    lignes_de_remboursement = LigneArticle.objects.filter(
        paiement_stripe_id=ligne.paiement_stripe_id,
        qty__lt=0,
        metadata__original_lignearticle_uuid=str(ligne.uuid),
    )
    assert lignes_de_remboursement.count() == 1, (
        f"Une ligne de remboursement attendue pour la ligne {ligne.uuid}, "
        f"{lignes_de_remboursement.count()} trouvée(s)."
    )
    return lignes_de_remboursement.get()


def verifier_l_article_rembourse(avoir, ligne_d_origine, quantite_rendue):
    """
    Vérifie l'article d'avoir écrit par un remboursement Stripe : statut REFUNDED, lié à
    la ligne d'origine, même prix unitaire, quantité négative, montants miroirs, relié au
    paiement Stripe, et dans une vente.
    / Checks a Stripe refund item: REFUNDED, linked to the original line, same unit
    price, negative quantity, mirrored amounts, linked to the Stripe payment, in a sale.
    """
    assert avoir.vente_id is not None, "La ligne remboursée n'a pas de vente."
    assert avoir.credit_note_for_id == ligne_d_origine.pk
    assert avoir.status == LigneArticle.REFUNDED
    assert avoir.pricesold_id == ligne_d_origine.pricesold_id
    assert avoir.amount == ligne_d_origine.amount
    assert avoir.qty == -Decimal(quantite_rendue)
    total_rendu_attendu = -ligne_d_origine.amount * quantite_rendue
    assert avoir.total_catalogue == total_rendu_attendu
    assert avoir.part_offerte == 0
    assert avoir.total_ttc == total_rendu_attendu
    assert avoir.paiement_stripe_id == ligne_d_origine.paiement_stripe_id


def verifier_le_reglement_stripe_du_remboursement(vente_d_avoir, paiement, remboursement):
    """
    Vérifie l'UNIQUE règlement de la vente d'avoir : au moyen du paiement Stripe
    d'origine, montant = −montant RENVOYÉ par Stripe, référence externe = identifiant du
    remboursement, relié au paiement.
    / Checks the ONLY payment of the credit note sale: original Stripe method, amount =
    −amount RETURNED by Stripe, external reference = refund id, linked to the payment.
    """
    paiement.refresh_from_db()
    assert paiement.moyen, "Le paiement Stripe d'origine n'a pas de moyen."
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (paiement.moyen, -remboursement.amount)
    ]
    reglement_du_remboursement = vente_d_avoir.reglements.get()
    assert reglement_du_remboursement.reference_externe == remboursement.id
    assert reglement_du_remboursement.paiement_stripe_id == paiement.pk


def erreurs_journalisees_du_remboursement(caplog):
    """Les enregistrements ERROR (ou plus) des journaux du remboursement Stripe.
    / ERROR (or higher) records of the Stripe refund loggers."""
    erreurs = []
    for enregistrement in caplog.records:
        journal_du_remboursement = enregistrement.name in JOURNAUX_DU_REMBOURSEMENT_STRIPE
        if journal_du_remboursement and enregistrement.levelno >= logging.ERROR:
            erreurs.append(enregistrement)
    return erreurs


def rien_n_est_ecrit_pour_le_remboursement(ligne, paiement, statut_du_paiement_avant):
    """
    Vérifie qu'un remboursement n'a RIEN écrit : aucun avoir pour la ligne (voir
    `rien_n_est_ecrit_pour_la_ligne`), aucune ligne négative sur le paiement Stripe, et le
    paiement garde son statut.
    / Checks a refund wrote NOTHING: no credit note, no negative line on the Stripe
    payment, and the payment keeps its status.
    """
    rien_n_est_ecrit_pour_la_ligne(ligne)
    assert not LigneArticle.objects.filter(
        paiement_stripe=paiement, qty__lt=0
    ).exists(), "Une ligne négative a été écrite sur le paiement Stripe."
    paiement.refresh_from_db()
    assert paiement.status == statut_du_paiement_avant


def vendre_en_ligne_une_entree_en_partie_offerte():
    """
    ÉTAT DE DÉPART : une vente en ligne réglée par Stripe, écrite par le service de vente.
    Deux entrées à 10 € (catalogue 2000), dont 10 € offerts (part offerte 1000, source
    OFFRIR) : net 1000. Règlements : Stripe 1000 (relié au paiement) et FREE 1000. Le
    paiement Stripe est VALID, au moyen « Stripe » (`SN`), lié à la vente.
    Rend la ligne et son paiement.
    / STARTING STATE: a settled online sale paid by Stripe: two 10 € entries, 10 € of
    which offered (net 1000). Returns the line and its payment.
    """
    acheteur = creer_utilisateur()
    tarif_vendu = creer_tarif_vendu(nom="Entrée en partie offerte", prix_en_euros="10.00")
    vente_en_ligne = services_vente.ouvrir_vente(
        origine=SaleOrigin.LESPASS,
        nature=Vente.Nature.VENTE,
        client=acheteur,
    )
    # Une création : aucune transition de la machine à états ne part.
    # / A creation: no state machine transition runs.
    paiement = Paiement_stripe.objects.create(
        user=acheteur,
        status=Paiement_stripe.VALID,
        moyen=PaymentMethod.STRIPE_NOFED,
        payment_intent_id=f"pi_test_{identifiant_unique()}",
        vente=vente_en_ligne,
    )
    ligne = services_vente.ajouter_article(
        vente_en_ligne,
        pricesold=tarif_vendu,
        quantite=Decimal("2"),
        prix_unitaire=1000,
        taux_tva=Decimal("20"),
        part_offerte=1000,
        source_offert=LigneArticle.SourceOffert.OFFRIR,
        payment_method=PaymentMethod.STRIPE_NOFED,
        paiement_stripe=paiement,
        status=LigneArticle.VALID,
    )
    services_vente.ajouter_reglement(
        vente_en_ligne,
        moyen=PaymentMethod.STRIPE_NOFED,
        montant=1000,
        paiement_stripe=paiement,
    )
    services_vente.ajouter_reglement(
        vente_en_ligne, moyen=PaymentMethod.FREE, montant=1000
    )
    services_vente.encaisser_vente(vente_en_ligne)
    return SimpleNamespace(ligne=ligne, paiement=paiement)


def test_remboursement_stripe_partiel_avoir_montant_du_refund(lieu):
    """
    Fiche test 17. Trois billets à 10 € payés par Stripe ; UN billet est annulé
    (`cancel_and_refund_ticket`) : un remboursement Stripe partiel.
    - Stripe est appelé UNE fois, pour 1000 centimes.
    - UN article d'avoir : quantité −1, prix unitaire 1000, net −1000, lié à la ligne
      d'origine et au paiement Stripe, statut REFUNDED.
    - La vente AVOIR : origine LESPASS, réglée, numérotée, liée à la vente du paiement,
      même client.
    - UN règlement : −montant renvoyé par Stripe, au moyen du paiement, référence
      externe = identifiant du remboursement, relié au paiement.
    - Ordre : à l'encaissement, l'article est encore CREATED ; il passe REFUNDED après.
    - Le paiement passe « remboursé en partie ».
    / Test 17: one ticket out of three refunded through Stripe: one AVOIR sale, linked,
    one item qty −1, one payment of −refund.amount with the refund id; REFUNDED after
    the settlement.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=3)
    ligne_d_origine = LigneArticle.objects.get(paiement_stripe=achat.paiement)
    vente_d_origine = Vente.objects.get(pk=ligne_d_origine.vente_id)
    reservation = Reservation.objects.get(pk=achat.reservation.pk)
    billet_a_annuler = reservation.tickets.order_by("pk").first()

    with remboursement_stripe_simule() as stripe_simule:
        with statuts_des_articles_a_l_encaissement() as statuts_releves:
            reservation.cancel_and_refund_ticket(billet_a_annuler)

    assert stripe_simule.appels.call_count == 1
    assert stripe_simule.appels.call_args.kwargs["amount"] == 1000
    remboursement = stripe_simule.remboursements_rendus[0]

    avoir = le_remboursement_de_la_ligne(ligne_d_origine)
    verifier_l_article_rembourse(avoir, ligne_d_origine, quantite_rendue=1)
    assert avoir.reservation_id == reservation.pk

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
        origine_attendue=SaleOrigin.LESPASS,
    )
    assert vente_d_avoir.articles.count() == 1
    verifier_le_reglement_stripe_du_remboursement(
        vente_d_avoir, achat.paiement, remboursement
    )

    # Un seul encaissement : celui de l'avoir, article encore CREATED.
    # / One settlement: the credit note's, item still CREATED.
    assert statuts_releves == [[LigneArticle.CREATED]]

    achat.paiement.refresh_from_db()
    assert achat.paiement.status == Paiement_stripe.PARTIALLY_REFUNDED
    verifier_egalites(vente_d_avoir)


def test_remboursement_stripe_total_reservation_une_vente_avoir(lieu):
    """
    Une réservation payée par Stripe, DEUX lignes : 2 billets à 10 € et 1 billet réduit
    à 5 € (2500). Toute la réservation est annulée (`cancel_and_refund_resa`).
    - Stripe est appelé UNE fois, pour 2500.
    - UNE seule vente AVOIR, avec DEUX articles (−2000 et −500), tous deux REFUNDED.
    - UN seul règlement : −2500, référence = identifiant du remboursement.
    - À l'encaissement, les deux articles sont encore CREATED.
    - Le paiement passe « remboursé ».
    / A two-line reservation fully refunded: one Stripe call, ONE AVOIR sale with two
    items, ONE payment of −2500.
    """
    achat = reserver_des_billets_a_payer(lieu)
    revenir_de_stripe_billetterie(achat.client, achat.paiement)
    lignes_d_origine = list(
        LigneArticle.objects.filter(paiement_stripe=achat.paiement).order_by("-amount")
    )
    assert len(lignes_d_origine) == 2
    ligne_tarif_plein = lignes_d_origine[0]
    ligne_tarif_reduit = lignes_d_origine[1]
    vente_d_origine = Vente.objects.get(pk=ligne_tarif_plein.vente_id)
    reservation = Reservation.objects.get(pk=achat.reservation.pk)

    with remboursement_stripe_simule() as stripe_simule:
        with statuts_des_articles_a_l_encaissement() as statuts_releves:
            reservation.cancel_and_refund_resa()

    assert stripe_simule.appels.call_count == 1
    assert stripe_simule.appels.call_args.kwargs["amount"] == 2500
    remboursement = stripe_simule.remboursements_rendus[0]

    avoir_tarif_plein = le_remboursement_de_la_ligne(ligne_tarif_plein)
    avoir_tarif_reduit = le_remboursement_de_la_ligne(ligne_tarif_reduit)
    verifier_l_article_rembourse(avoir_tarif_plein, ligne_tarif_plein, quantite_rendue=2)
    verifier_l_article_rembourse(
        avoir_tarif_reduit, ligne_tarif_reduit, quantite_rendue=1
    )
    assert avoir_tarif_plein.vente_id == avoir_tarif_reduit.vente_id, (
        "Les deux lignes remboursées doivent être dans la même vente AVOIR."
    )

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir_tarif_plein,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
        origine_attendue=SaleOrigin.LESPASS,
    )
    assert vente_d_avoir.articles.count() == 2
    verifier_le_reglement_stripe_du_remboursement(
        vente_d_avoir, achat.paiement, remboursement
    )
    assert statuts_releves == [[LigneArticle.CREATED, LigneArticle.CREATED]]

    achat.paiement.refresh_from_db()
    assert achat.paiement.status == Paiement_stripe.REFUNDED
    verifier_egalites(vente_d_avoir)


def test_remboursement_stripe_montant_different_ecart_d_encaissement(lieu, caplog):
    """
    Un billet à 10 € payé par Stripe, remboursé en entier. Stripe reçoit une demande de
    1000 mais annonce 900 rendus (frais, arrondi).
    - L'article d'avoir vaut −1000 (le billet rendu, au prix vendu).
    - UN règlement : −900, le montant RENVOYÉ par Stripe, jamais le montant calculé.
    - L'écart (+100 : rendu en moins, donc gardé en plus) devient un article « Écart
      d'encaissement — reçu en plus » : quantité +1, prix 100, TVA 0, hors chiffre
      d'affaires, VALID, sans paiement Stripe.
    - Une alerte est journalisée (ERROR).
    / Stripe returns 900 for 1000 asked: a −900 payment, the −1000 item, and a "received
    more" gap item of +100; an ERROR alert is logged.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=1)
    ligne_d_origine = LigneArticle.objects.get(paiement_stripe=achat.paiement)
    vente_d_origine = Vente.objects.get(pk=ligne_d_origine.vente_id)
    reservation = Reservation.objects.get(pk=achat.reservation.pk)

    with remboursement_stripe_simule(montant_rendu_par_stripe=900) as stripe_simule:
        reservation.cancel_and_refund_resa()

    assert stripe_simule.appels.call_count == 1
    assert stripe_simule.appels.call_args.kwargs["amount"] == 1000
    remboursement = stripe_simule.remboursements_rendus[0]

    avoir = le_remboursement_de_la_ligne(ligne_d_origine)
    verifier_l_article_rembourse(avoir, ligne_d_origine, quantite_rendue=1)

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
        origine_attendue=SaleOrigin.LESPASS,
    )
    verifier_le_reglement_stripe_du_remboursement(
        vente_d_avoir, achat.paiement, remboursement
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir)[0][1] == -900

    articles_d_ecart = articles_d_ecart_de_la_vente(vente_d_avoir)
    assert len(articles_d_ecart) == 1
    verifier_l_article_d_ecart(
        articles_d_ecart[0],
        nom_attendu=NOM_ECART_RECU_EN_PLUS,
        quantite_attendue=1,
        ecart_en_centimes=100,
    )
    assert len(erreurs_journalisees_du_remboursement(caplog)) >= 1

    verifier_egalites(vente_d_avoir)


def test_remboursement_stripe_avoir_partiel_d_un_offert_refuse_avant_stripe(lieu):
    """
    Une ligne payée par Stripe : deux entrées à 10 €, dont 10 € offerts. On demande le
    remboursement d'UNE seule entrée (`specified_quantity=1`). Le service refuse
    (ValueError « rembourser l'article entier » : aucun prorata d'offert), et ce refus
    arrive AVANT Stripe :
    - `stripe.Refund.create` n'est JAMAIS appelé ;
    - rien n'est écrit : aucun avoir, aucune vente AVOIR, aucune ligne négative, le
      paiement reste VALID, la ligne reste VALID.
    / A partial refund of an item with an offered part is refused by the service BEFORE
    Stripe: no Stripe call, nothing written.
    """
    entree_en_partie_offerte = vendre_en_ligne_une_entree_en_partie_offerte()
    ligne = entree_en_partie_offerte.ligne
    paiement = entree_en_partie_offerte.paiement

    with remboursement_stripe_simule() as stripe_simule:
        with pytest.raises(ValueError, match="rembourser l'article entier"):
            partial_refund_payment(
                paiement, Configuration.get_solo(), [ligne], specified_quantity=1
            )

    assert stripe_simule.appels.call_count == 0, (
        "Stripe a été appelé alors que le service refuse l'avoir."
    )
    rien_n_est_ecrit_pour_le_remboursement(
        ligne, paiement, statut_du_paiement_avant=Paiement_stripe.VALID
    )


def test_remboursement_stripe_echec_d_encaissement_rien_n_est_ecrit(lieu, caplog):
    """
    Deux billets à 10 € payés par Stripe, remboursés en entier. Stripe rend l'argent,
    puis l'encaissement de la vente AVOIR échoue (simulé). Règle « 500 + Sentry » :
    - l'erreur remonte à l'appelant, et elle est journalisée (ERROR) ;
    - rien n'est écrit : aucun avoir, aucune vente AVOIR, aucune ligne négative ; le
      paiement garde son statut, la ligne reste VALID.
    / Stripe refunds, then the AVOIR settlement fails (faked): the error is raised and
    logged, nothing is written.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=2)
    ligne = LigneArticle.objects.get(paiement_stripe=achat.paiement)
    paiement = Paiement_stripe.objects.get(pk=achat.paiement.pk)
    statut_du_paiement_avant = paiement.status

    with remboursement_stripe_simule() as stripe_simule:
        with encaissement_qui_echoue():
            with pytest.raises(Exception):
                partial_refund_payment(paiement, Configuration.get_solo(), [ligne])

    # Stripe a été appelé : l'échec arrive APRÈS le remboursement.
    # / Stripe was called: the failure comes AFTER the refund.
    assert stripe_simule.appels.call_count == 1
    remboursement = stripe_simule.remboursements_rendus[0]

    # L'erreur journalisée porte l'identifiant du remboursement Stripe : un humain
    # rapproche à la main l'argent rendu, qu'aucune vente ne trace.
    # / The logged error carries the Stripe refund id, for a manual reconciliation.
    messages_d_erreur = []
    for enregistrement in erreurs_journalisees_du_remboursement(caplog):
        messages_d_erreur.append(enregistrement.getMessage())
    erreur_avec_l_id_du_remboursement = False
    for message_d_erreur in messages_d_erreur:
        if remboursement.id in message_d_erreur:
            erreur_avec_l_id_du_remboursement = True
    assert erreur_avec_l_id_du_remboursement, (
        f"Aucune erreur journalisée ne cite le remboursement {remboursement.id} : "
        f"{messages_d_erreur}"
    )
    rien_n_est_ecrit_pour_le_remboursement(ligne, paiement, statut_du_paiement_avant)


def test_remboursement_stripe_vente_d_origine_pas_reglee_refuse_avant_stripe(lieu):
    """
    Une ligne payée par Stripe dont la vente d'origine existe mais n'est pas réglée (EN
    ATTENTE). Le remboursement est refusé (ValueError « pas réglée ») AVANT Stripe :
    - `stripe.Refund.create` n'est JAMAIS appelé ;
    - rien n'est écrit : aucun avoir, aucune vente AVOIR, aucune ligne négative, le
      paiement et la ligne gardent leur statut.
    / A line whose original sale is not settled: the refund is refused BEFORE Stripe,
    nothing is written.
    """
    acheteur = creer_utilisateur()
    tarif_vendu = creer_tarif_vendu(nom="Vente pas réglée", prix_en_euros="10.00")
    # ÉTAT DE DÉPART : une vente en ligne ouverte, avec son article payé par Stripe,
    # jamais encaissée.
    # / STARTING STATE: an open online sale, its Stripe-paid item, never settled.
    vente_en_attente = services_vente.ouvrir_vente(
        origine=SaleOrigin.LESPASS,
        nature=Vente.Nature.VENTE,
        client=acheteur,
    )
    paiement = Paiement_stripe.objects.create(
        user=acheteur,
        status=Paiement_stripe.VALID,
        moyen=PaymentMethod.STRIPE_NOFED,
        payment_intent_id=f"pi_test_{identifiant_unique()}",
        vente=vente_en_attente,
    )
    ligne = services_vente.ajouter_article(
        vente_en_attente,
        pricesold=tarif_vendu,
        quantite=Decimal("1"),
        prix_unitaire=1000,
        taux_tva=Decimal("20"),
        payment_method=PaymentMethod.STRIPE_NOFED,
        paiement_stripe=paiement,
        status=LigneArticle.VALID,
    )

    with remboursement_stripe_simule() as stripe_simule:
        with pytest.raises(ValueError, match="pas réglée"):
            partial_refund_payment(paiement, Configuration.get_solo(), [ligne])

    assert stripe_simule.appels.call_count == 0, (
        "Stripe a été appelé alors que la vente d'origine n'est pas réglée."
    )
    rien_n_est_ecrit_pour_le_remboursement(
        ligne, paiement, statut_du_paiement_avant=Paiement_stripe.VALID
    )


def test_remboursement_stripe_booking_pose_la_fk_booking(lieu):
    """
    Fiche test 21, côté Stripe. Un créneau d'une heure d'une ressource à 12 €/h, payé
    par Stripe (sans panier), puis annulé par la personne (`cancel_and_refund_booking`).
    - L'article d'avoir porte le booking (FK `booking`), quantité −1, net −1200,
      REFUNDED.
    - La vente AVOIR : liée à la vente du booking, réglée ; UN règlement −1200 avec
      l'identifiant du remboursement.
    / Sheet test 21, Stripe side: the refunded booking's item carries the booking FK; one
    AVOIR sale, one −1200 payment with the refund id.
    """
    acheteur = creer_utilisateur()
    client_de_l_acheteur = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="12.00")
    reserver_une_ressource_sans_panier(client_de_l_acheteur, location)
    booking = Booking.objects.get(user=acheteur, resource=location.ressource)
    paiement = Paiement_stripe.objects.get(booking=booking)
    revenir_de_stripe_billetterie(client_de_l_acheteur, paiement)
    booking.refresh_from_db()
    assert booking.status == Booking.PAID_BY_USER
    ligne_du_booking = LigneArticle.objects.get(booking=booking, qty__gt=0)
    vente_d_origine = Vente.objects.get(pk=ligne_du_booking.vente_id)

    with remboursement_stripe_simule() as stripe_simule:
        booking.cancel_and_refund_booking()

    assert stripe_simule.appels.call_count == 1
    assert stripe_simule.appels.call_args.kwargs["amount"] == 1200
    remboursement = stripe_simule.remboursements_rendus[0]

    avoir = le_remboursement_de_la_ligne(ligne_du_booking)
    verifier_l_article_rembourse(avoir, ligne_du_booking, quantite_rendue=1)
    assert avoir.booking_id == booking.pk

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
        origine_attendue=SaleOrigin.LESPASS,
    )
    verifier_le_reglement_stripe_du_remboursement(vente_d_avoir, paiement, remboursement)
    verifier_egalites(vente_d_avoir)


def test_remboursement_stripe_rien_a_rendre_aucune_vente_ouverte(lieu):
    """
    Une ligne payée par Stripe dont la quantité à rendre vaut 0 (`to_refund_qty`, posé
    par l'appelant quand tous les billets du tarif sont déjà annulés). Rien à rendre :
    - `stripe.Refund.create` n'est pas appelé ;
    - AUCUNE vente AVOIR n'est ouverte (pas de vente vide) ; rien n'est écrit.
    / A line with nothing to give back: no Stripe call, NO AVOIR sale opened, nothing
    written.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=1)
    ligne = LigneArticle.objects.get(paiement_stripe=achat.paiement)
    paiement = Paiement_stripe.objects.get(pk=achat.paiement.pk)
    statut_du_paiement_avant = paiement.status
    nombre_de_ventes_avoir_avant = Vente.objects.filter(
        nature=Vente.Nature.AVOIR
    ).count()
    ligne.to_refund_qty = 0

    with remboursement_stripe_simule() as stripe_simule:
        partial_refund_payment(paiement, Configuration.get_solo(), [ligne])

    assert stripe_simule.appels.call_count == 0
    assert (
        Vente.objects.filter(nature=Vente.Nature.AVOIR).count()
        == nombre_de_ventes_avoir_avant
    ), "Une vente AVOIR a été ouverte alors qu'il n'y a rien à rendre."
    rien_n_est_ecrit_pour_le_remboursement(ligne, paiement, statut_du_paiement_avant)


# --------------------------------------------------------------------------
# Remboursement Stripe : jamais deux fois le même argent
# / Stripe refund: never the same money twice
# --------------------------------------------------------------------------


@contextmanager
def remboursement_stripe_qui_respecte_la_cle_d_idempotence():
    """
    Remplace `stripe.Refund.create` le temps du bloc, comme Stripe le fait avec une clé
    d'idempotence : un appel avec une clé DÉJÀ VUE rend le MÊME remboursement (même
    identifiant), sans rendre d'argent de plus. Un appel sans clé, ou avec une clé
    nouvelle, rend un remboursement nouveau.
    / Replaces `stripe.Refund.create` like Stripe with an idempotency key: a key already
    seen returns the SAME refund; no key, or a new key, returns a new refund.

    :return: un objet avec `appels` (le faux `Refund.create`) et `remboursements_rendus`
        (les objets rendus, dans l'ordre des appels)
    """
    remboursements_par_cle = {}
    remboursements_rendus = []

    def rembourser(**arguments_du_remboursement):
        cle_d_idempotence = arguments_du_remboursement.get("idempotency_key")
        cle_deja_vue = (
            cle_d_idempotence is not None and cle_d_idempotence in remboursements_par_cle
        )
        if cle_deja_vue:
            remboursement = remboursements_par_cle[cle_d_idempotence]
        else:
            remboursement = rembourser_comme_stripe(**arguments_du_remboursement)
            if cle_d_idempotence is not None:
                remboursements_par_cle[cle_d_idempotence] = remboursement
        remboursements_rendus.append(remboursement)
        return remboursement

    with patch("stripe.Refund.create", side_effect=rembourser) as appels_a_stripe:
        yield SimpleNamespace(
            appels=appels_a_stripe,
            remboursements_rendus=remboursements_rendus,
        )


def cles_d_idempotence_envoyees(appels_a_stripe):
    """Les clés d'idempotence reçues par `stripe.Refund.create`, dans l'ordre (None si
    absente). / The idempotency keys received, in order (None when missing)."""
    cles = []
    for appel in appels_a_stripe.call_args_list:
        cles.append(appel.kwargs.get("idempotency_key"))
    return cles


def cle_d_idempotence_attendue(paiement, nombre_de_remboursements_deja_ecrits):
    """La clé décidée en D-3z : `remboursement-{uuid du paiement}-{n}`.
    / The key decided in D-3z."""
    return f"remboursement-{paiement.uuid}-{nombre_de_remboursements_deja_ecrits}"


def test_remboursement_stripe_deux_fois_la_meme_ligne_refuse_le_second_avant_stripe(lieu):
    """
    Un billet à 10 € payé par Stripe. Deux demandes de remboursement de toute la ligne
    arrivent (double clic) : chacune a lu la ligne AVANT que l'autre n'écrive.
    - La première rembourse : Stripe est appelé une fois, une vente AVOIR est écrite.
    - La seconde est refusée (ValueError) AVANT Stripe : `partial_refund_payment` relit,
      sous verrou, la quantité déjà rendue ; il ne reste rien.
    - Stripe n'est appelé qu'UNE fois ; une seule ligne négative sur le paiement.
    / Two refund requests for the same line: the second one is refused BEFORE Stripe
    (quantity given back read again under lock); one Stripe call, one negative line.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=1)
    ligne_lue_par_la_premiere_demande = LigneArticle.objects.get(
        paiement_stripe=achat.paiement
    )
    ligne_lue_par_la_seconde_demande = LigneArticle.objects.get(
        pk=ligne_lue_par_la_premiere_demande.pk
    )
    paiement_lu_par_la_premiere_demande = Paiement_stripe.objects.get(pk=achat.paiement.pk)
    paiement_lu_par_la_seconde_demande = Paiement_stripe.objects.get(pk=achat.paiement.pk)

    with remboursement_stripe_simule() as stripe_simule:
        partial_refund_payment(
            paiement_lu_par_la_premiere_demande,
            Configuration.get_solo(),
            [ligne_lue_par_la_premiere_demande],
        )
        with pytest.raises(ValueError):
            partial_refund_payment(
                paiement_lu_par_la_seconde_demande,
                Configuration.get_solo(),
                [ligne_lue_par_la_seconde_demande],
            )

    assert stripe_simule.appels.call_count == 1, (
        "Stripe a été appelé deux fois pour la même ligne."
    )
    assert (
        LigneArticle.objects.filter(paiement_stripe=achat.paiement, qty__lt=0).count()
        == 1
    )


def test_remboursement_stripe_nouvel_essai_reprend_la_meme_cle(lieu):
    """
    Deux billets à 10 € payés par Stripe, remboursés en entier.
    - 1er essai : Stripe rend l'argent, puis l'encaissement de la vente AVOIR échoue
      (simulé) : rien n'est écrit.
    - 2e essai, normal : `stripe.Refund.create` reçoit la MÊME clé d'idempotence,
      `remboursement-{paiement}-0` (aucun règlement négatif écrit entre les deux). Stripe
      rend donc le MÊME remboursement : aucun argent de plus.
    - La vente AVOIR est écrite UNE fois ; son règlement porte l'identifiant de ce
      remboursement unique.
    / First try: Stripe refunds, then the settlement fails, nothing written. Retry: the
    SAME idempotency key, so the SAME refund; the AVOIR sale is written once, with that
    refund's id.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=2)
    ligne = LigneArticle.objects.get(paiement_stripe=achat.paiement)
    vente_d_origine = Vente.objects.get(pk=ligne.vente_id)
    paiement = Paiement_stripe.objects.get(pk=achat.paiement.pk)
    statut_du_paiement_avant = paiement.status

    with remboursement_stripe_qui_respecte_la_cle_d_idempotence() as stripe_simule:
        with encaissement_qui_echoue():
            with pytest.raises(Exception):
                partial_refund_payment(paiement, Configuration.get_solo(), [ligne])
        rien_n_est_ecrit_pour_le_remboursement(ligne, paiement, statut_du_paiement_avant)

        partial_refund_payment(
            Paiement_stripe.objects.get(pk=paiement.pk),
            Configuration.get_solo(),
            [LigneArticle.objects.get(pk=ligne.pk)],
        )

    cle_du_premier_remboursement = cle_d_idempotence_attendue(paiement, 0)
    assert cles_d_idempotence_envoyees(stripe_simule.appels) == [
        cle_du_premier_remboursement,
        cle_du_premier_remboursement,
    ]
    identifiants_des_remboursements = set()
    for remboursement_rendu in stripe_simule.remboursements_rendus:
        identifiants_des_remboursements.add(remboursement_rendu.id)
    assert len(identifiants_des_remboursements) == 1, (
        "Stripe a fait deux remboursements différents pour le même argent."
    )
    remboursement_unique = stripe_simule.remboursements_rendus[0]

    avoir = le_remboursement_de_la_ligne(ligne)
    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
        origine_attendue=SaleOrigin.LESPASS,
    )
    assert (
        Vente.objects.filter(
            nature=Vente.Nature.AVOIR, vente_liee=vente_d_origine
        ).count()
        == 1
    )
    verifier_le_reglement_stripe_du_remboursement(
        vente_d_avoir, paiement, remboursement_unique
    )
    verifier_egalites(vente_d_avoir)


def test_remboursement_stripe_second_remboursement_cle_nouvelle(lieu):
    """
    Trois billets à 10 € payés par Stripe. Deux billets sont annulés l'un après l'autre
    (`cancel_and_refund_ticket`) : deux remboursements Stripe.
    - Le premier porte la clé `remboursement-{paiement}-0` (aucun règlement négatif
      écrit avant lui).
    - Le second, une fois le premier écrit, porte une clé NOUVELLE :
      `remboursement-{paiement}-1`. Stripe fait donc bien un second remboursement.
    / Two tickets refunded one after the other: keys `-0` then `-1`, two refunds.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=3)
    reservation = Reservation.objects.get(pk=achat.reservation.pk)
    billets_dans_l_ordre = list(reservation.tickets.order_by("pk"))
    premier_billet_annule = billets_dans_l_ordre[0]
    second_billet_annule = billets_dans_l_ordre[1]

    with remboursement_stripe_qui_respecte_la_cle_d_idempotence() as stripe_simule:
        reservation.cancel_and_refund_ticket(premier_billet_annule)
        reservation.cancel_and_refund_ticket(second_billet_annule)

    assert cles_d_idempotence_envoyees(stripe_simule.appels) == [
        cle_d_idempotence_attendue(achat.paiement, 0),
        cle_d_idempotence_attendue(achat.paiement, 1),
    ]
    assert (
        Reglement.objects.filter(paiement_stripe=achat.paiement, montant__lt=0).count()
        == 2
    ), "Les deux remboursements doivent être écrits."


# --------------------------------------------------------------------------
# Annulations par l'admin : l'écran « Remboursé par », puis un avoir par ligne
# / Admin cancellations: the "Refunded by" screen, then one credit note per line
# --------------------------------------------------------------------------

URL_DE_LA_LISTE_DES_RESERVATIONS = "/admin/BaseBillet/reservation/"
URL_DE_LA_LISTE_DES_BILLETS = "/admin/BaseBillet/ticket/"
ACTION_ANNULER_LES_RESERVATIONS = "action_cancel_refund_reservations"
ACTION_ANNULER_LES_BILLETS = "action_cancel_refund_selected"


def donnees_de_l_action(nom_de_l_action, objets_coches):
    """
    Les données que la liste de l'admin poste quand l'admin coche des objets et lance
    une action : le nom de l'action et les clés des objets cochés.
    / The data the admin list posts for an action: its name and the ticked keys.
    """
    cles_des_objets_coches = []
    for objet_coche in objets_coches:
        cles_des_objets_coches.append(str(objet_coche.pk))
    return {
        "action": nom_de_l_action,
        "_selected_action": cles_des_objets_coches,
    }


def lancer_l_action_d_annulation(
    client_de_l_admin, url_de_la_liste, nom_de_l_action, objets_coches
):
    """
    1er POST : l'admin coche les objets et lance l'action d'annulation. L'écran
    d'annulation doit s'ouvrir (200) ; rien n'est encore annulé.
    / First POST: the admin ticks and runs the cancel action; the screen must open.
    """
    return client_de_l_admin.post(
        url_de_la_liste, donnees_de_l_action(nom_de_l_action, objets_coches)
    )


def confirmer_l_ecran_d_annulation(
    client_de_l_admin,
    url_de_la_liste,
    nom_de_l_action,
    objets_coches,
    moyen_rembourse=None,
):
    """
    2e POST : l'admin valide l'écran. Mêmes données que le 1er POST, plus `post=yes`
    (la confirmation, comme l'écran de suppression de Django) et le moyen « Remboursé
    par » s'il est donné.
    / Second POST: same data plus `post=yes` and the "Refunded by" method if given.
    """
    donnees_du_formulaire = donnees_de_l_action(nom_de_l_action, objets_coches)
    donnees_du_formulaire["post"] = "yes"
    if moyen_rembourse is not None:
        donnees_du_formulaire["moyen_rembourse"] = moyen_rembourse
    return client_de_l_admin.post(url_de_la_liste, donnees_du_formulaire)


def statuts_des_billets(reservation):
    """Les statuts des billets de la réservation, triés. / Sorted ticket statuses."""
    statuts = []
    for billet in Ticket.objects.filter(reservation=reservation):
        statuts.append(billet.status)
    return sorted(statuts)


def rien_n_est_annule(reservation, statut_de_la_reservation_avant, statuts_des_billets_avant):
    """
    Vérifie que l'annulation n'a rien changé : la réservation et ses billets gardent
    leurs statuts.
    / Checks the cancellation changed nothing: same reservation and ticket statuses.
    """
    reservation.refresh_from_db()
    assert reservation.status == statut_de_la_reservation_avant
    assert statuts_des_billets(reservation) == statuts_des_billets_avant


def test_annulation_admin_reservation_especes_avoir_au_moyen_choisi(lieu):
    """
    Deux billets à 10 € vendus dans l'admin, payés par CB (`CC`). L'admin coche la
    réservation et lance « Annuler et rembourser ».
    - L'écran s'ouvre : champ « Remboursé par », pré-rempli avec CB (le moyen d'origine
      est dans la liste). Rien n'est encore annulé.
    - L'admin choisit « espèces » (`CA`) et valide : réservation et billets annulés, le
      mail d'annulation est demandé.
    - L'avoir : quantité −2, prix unitaire 1000, net −2000, CREDIT_NOTE ; sa vente AVOIR
      (origine ADMIN) est réglée, liée à la vente d'origine, même client ; UN règlement
      espèces −2000.
    / Admin card sale cancelled through the screen, refunded in cash: one AVOIR sale with
    one cash payment of −2000; reservation and tickets cancelled.
    """
    vente_admin = vendre_et_relire(
        lieu, prix="10.00", quantite=2, moyen_de_paiement=PaymentMethod.CC
    )
    reservation = vente_admin.reservation
    ligne_d_origine = vente_admin.ligne
    vente_d_origine = Vente.objects.get(pk=ligne_d_origine.vente_id)
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    statut_de_la_reservation_avant = reservation.status
    statuts_des_billets_avant = statuts_des_billets(reservation)
    lieu.taches_demandees.clear()

    reponse_de_l_ecran = lancer_l_action_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_RESERVATIONS,
        ACTION_ANNULER_LES_RESERVATIONS,
        [reservation],
    )
    assert "moyen_rembourse" in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)
    assert valeur_pre_remplie_du_moyen(reponse_de_l_ecran) == PaymentMethod.CC
    # Ouvrir l'écran n'annule rien. / Opening the screen cancels nothing.
    rien_n_est_annule(
        reservation, statut_de_la_reservation_avant, statuts_des_billets_avant
    )
    rien_n_est_ecrit_pour_la_ligne(ligne_d_origine)

    reponse_de_l_action = confirmer_l_ecran_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_RESERVATIONS,
        ACTION_ANNULER_LES_RESERVATIONS,
        [reservation],
        moyen_rembourse=PaymentMethod.CASH,
    )

    assert reponse_de_l_action.status_code == 302
    reservation.refresh_from_db()
    assert reservation.status == Reservation.CANCELED
    assert statuts_des_billets(reservation) == [Ticket.CANCELED, Ticket.CANCELED]
    assert "send_reservation_cancellation_user" in noms_des_taches(
        lieu.taches_demandees
    )
    assert lieu.remboursement_stripe.call_count == 0

    avoir = l_avoir_de_la_ligne(ligne_d_origine)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.qty == Decimal("-2")
    assert avoir.amount == 1000
    assert avoir.total_ttc == -2000
    assert avoir.reservation_id == reservation.pk

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.CASH, -2000)
    ]
    verifier_egalites(vente_d_avoir)


def test_annulation_admin_ecran_sans_champ_pour_une_reservation_stripe(lieu):
    """
    Deux billets à 10 € payés en ligne par Stripe. L'admin coche la réservation et lance
    « Annuler et rembourser ».
    - L'écran s'ouvre SANS champ « Remboursé par » : l'argent est rendu par Stripe.
    - L'admin valide : Stripe est appelé UNE fois, pour 2000 ; la réservation est
      annulée ; le remboursement écrit sa vente AVOIR (D-3b), qui tient ses égalités.
    / Stripe-paid reservation: the screen has no "Refunded by" field; confirming refunds
    through Stripe once and cancels the reservation.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=2)
    reservation = Reservation.objects.get(pk=achat.reservation.pk)
    ligne_d_origine = LigneArticle.objects.get(paiement_stripe=achat.paiement)
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_ecran = lancer_l_action_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_RESERVATIONS,
        ACTION_ANNULER_LES_RESERVATIONS,
        [reservation],
    )
    assert "moyen_rembourse" not in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)

    with remboursement_stripe_simule() as stripe_simule:
        reponse_de_l_action = confirmer_l_ecran_d_annulation(
            client_de_l_admin,
            URL_DE_LA_LISTE_DES_RESERVATIONS,
            ACTION_ANNULER_LES_RESERVATIONS,
            [reservation],
        )

    assert reponse_de_l_action.status_code == 302
    assert stripe_simule.appels.call_count == 1
    assert stripe_simule.appels.call_args.kwargs["amount"] == 2000
    reservation.refresh_from_db()
    assert reservation.status == Reservation.CANCELED

    avoir = le_remboursement_de_la_ligne(ligne_d_origine)
    assert avoir.vente_id is not None, "La ligne remboursée n'a pas de vente."
    verifier_egalites(Vente.objects.get(pk=avoir.vente_id))


def test_annulation_admin_sans_moyen_refusee(lieu):
    """
    Deux billets à 10 € vendus dans l'admin en espèces. L'écran d'annulation affiche le
    champ « Remboursé par ». L'admin valide sans choisir de moyen :
    - l'écran revient (200), avec le champ ;
    - rien n'est annulé : réservation et billets gardent leurs statuts, aucun avoir,
      aucune vente AVOIR, la ligne reste VALID.
    / The field is shown but left empty: the screen comes back, nothing is cancelled.
    """
    vente_admin = vendre_et_relire(
        lieu, prix="10.00", quantite=2, moyen_de_paiement=PaymentMethod.CASH
    )
    reservation = vente_admin.reservation
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    statut_de_la_reservation_avant = reservation.status
    statuts_des_billets_avant = statuts_des_billets(reservation)

    reponse_de_l_ecran = lancer_l_action_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_RESERVATIONS,
        ACTION_ANNULER_LES_RESERVATIONS,
        [reservation],
    )
    assert "moyen_rembourse" in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)

    reponse_de_l_action = confirmer_l_ecran_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_RESERVATIONS,
        ACTION_ANNULER_LES_RESERVATIONS,
        [reservation],
        moyen_rembourse="",
    )

    assert "moyen_rembourse" in champs_du_formulaire_de_l_ecran(reponse_de_l_action)
    rien_n_est_annule(
        reservation, statut_de_la_reservation_avant, statuts_des_billets_avant
    )
    rien_n_est_ecrit_pour_la_ligne(vente_admin.ligne)


def test_annulation_admin_d_un_billet_avoir_d_une_unite(lieu):
    """
    Trois billets à 10 € vendus dans l'admin par CB. Dans la liste des billets, l'admin
    coche UN seul billet et lance « Annuler et rembourser ».
    - L'écran : champ « Remboursé par », pré-rempli avec CB.
    - L'admin choisit « virement » (`TR`) : ce billet est annulé, les deux autres restent
      actifs, la réservation n'est pas annulée ; le mail d'annulation du billet est
      demandé.
    - L'avoir : quantité −1, net −1000 ; sa vente AVOIR, liée, réglée : UN règlement
      virement −1000.
    / One ticket out of three cancelled from the ticket list, refunded by transfer: a
    one-unit credit note, one transfer payment of −1000.
    """
    vente_admin = vendre_et_relire(
        lieu, prix="10.00", quantite=3, moyen_de_paiement=PaymentMethod.CC
    )
    reservation = vente_admin.reservation
    ligne_d_origine = vente_admin.ligne
    vente_d_origine = Vente.objects.get(pk=ligne_d_origine.vente_id)
    billet_a_annuler = reservation.tickets.order_by("pk").first()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    statut_de_la_reservation_avant = reservation.status
    lieu.taches_demandees.clear()

    reponse_de_l_ecran = lancer_l_action_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_BILLETS,
        ACTION_ANNULER_LES_BILLETS,
        [billet_a_annuler],
    )
    assert "moyen_rembourse" in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)
    assert valeur_pre_remplie_du_moyen(reponse_de_l_ecran) == PaymentMethod.CC

    reponse_de_l_action = confirmer_l_ecran_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_BILLETS,
        ACTION_ANNULER_LES_BILLETS,
        [billet_a_annuler],
        moyen_rembourse=PaymentMethod.TRANSFER,
    )

    assert reponse_de_l_action.status_code == 302
    billet_a_annuler.refresh_from_db()
    assert billet_a_annuler.status == Ticket.CANCELED
    assert statuts_des_billets(reservation).count(Ticket.CANCELED) == 1
    reservation.refresh_from_db()
    assert reservation.status == statut_de_la_reservation_avant
    assert "send_ticket_cancellation_user" in noms_des_taches(lieu.taches_demandees)

    avoir = l_avoir_de_la_ligne(ligne_d_origine)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.qty == Decimal("-1")
    assert avoir.total_ttc == -1000

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.TRANSFER, -1000)
    ]
    verifier_egalites(vente_d_avoir)


def test_annulation_admin_d_un_billet_offert_sur_deux_permise(lieu):
    """
    Décision D-3c (d). Deux billets à 15 € « Offert » vendus dans l'admin (D32 : ligne
    au prix, entièrement offerte). L'admin annule UN des deux billets.
    - L'écran n'a PAS de champ « Remboursé par » : aucun argent à rendre.
    - L'avoir partiel d'une ligne ENTIÈREMENT offerte est permis : quantité −1,
      catalogue −1500, offert −1500, net 0, source OFFRIR.
    - Sa vente AVOIR, liée, réglée : UN seul règlement FREE −1500 (jamais deux).
    - Le billet est annulé, l'autre reste actif.
    / Cancelling one of two fully offered tickets is allowed: a one-unit credit note,
    fully offered, with ONE FREE payment of −1500; no "Refunded by" field.
    """
    vente_admin_offerte = vendre_et_relire(
        lieu, prix="15.00", quantite=2, moyen_de_paiement=PaymentMethod.FREE
    )
    reservation = vente_admin_offerte.reservation
    ligne_d_origine = vente_admin_offerte.ligne
    vente_d_origine = Vente.objects.get(pk=ligne_d_origine.vente_id)
    billet_a_annuler = reservation.tickets.order_by("pk").first()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_ecran = lancer_l_action_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_BILLETS,
        ACTION_ANNULER_LES_BILLETS,
        [billet_a_annuler],
    )
    assert "moyen_rembourse" not in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)

    reponse_de_l_action = confirmer_l_ecran_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_BILLETS,
        ACTION_ANNULER_LES_BILLETS,
        [billet_a_annuler],
    )

    assert reponse_de_l_action.status_code == 302
    billet_a_annuler.refresh_from_db()
    assert billet_a_annuler.status == Ticket.CANCELED
    assert statuts_des_billets(reservation).count(Ticket.CANCELED) == 1

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


def test_annulation_admin_deux_reservations_meme_moyen_ecran_pre_rempli(lieu):
    """
    L'admin coche DEUX réservations vendues dans l'admin et lance « Annuler et
    rembourser ». Un seul moyen vaut pour toute la sélection :
    - les deux payées en espèces (`CA`) : le champ « Remboursé par » est pré-rempli
      avec espèces ;
    - l'une par CB (`CC`), l'autre en espèces : moyens différents, le champ est vide.
    Ouvrir l'écran n'annule rien.
    / Two ticked reservations: the field is pre-filled when both share the same original
    method (cash), empty when they differ (card and cash). Opening cancels nothing.
    """
    premiere_vente_en_especes = vendre_et_relire(
        lieu, prix="10.00", quantite=1, moyen_de_paiement=PaymentMethod.CASH
    )
    seconde_vente_en_especes = vendre_et_relire(
        lieu, prix="12.00", quantite=1, moyen_de_paiement=PaymentMethod.CASH
    )
    vente_par_carte = vendre_et_relire(
        lieu, prix="8.00", quantite=1, moyen_de_paiement=PaymentMethod.CC
    )
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    ecran_meme_moyen = lancer_l_action_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_RESERVATIONS,
        ACTION_ANNULER_LES_RESERVATIONS,
        [premiere_vente_en_especes.reservation, seconde_vente_en_especes.reservation],
    )
    assert "moyen_rembourse" in champs_du_formulaire_de_l_ecran(ecran_meme_moyen)
    assert valeur_pre_remplie_du_moyen(ecran_meme_moyen) == PaymentMethod.CASH

    ecran_moyens_differents = lancer_l_action_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_RESERVATIONS,
        ACTION_ANNULER_LES_RESERVATIONS,
        [premiere_vente_en_especes.reservation, vente_par_carte.reservation],
    )
    assert "moyen_rembourse" in champs_du_formulaire_de_l_ecran(ecran_moyens_differents)
    assert valeur_pre_remplie_du_moyen(ecran_moyens_differents) in (None, "")

    # Ouvrir l'écran n'annule rien. / Opening the screen cancels nothing.
    for vente_admin in [premiere_vente_en_especes, seconde_vente_en_especes, vente_par_carte]:
        vente_admin.reservation.refresh_from_db()
        assert vente_admin.reservation.status != Reservation.CANCELED
        rien_n_est_ecrit_pour_la_ligne(vente_admin.ligne)


def test_annulation_admin_echec_d_encaissement_rien_n_est_annule(lieu):
    """
    Deux billets à 10 € vendus dans l'admin par CB. L'admin annule la réservation par
    l'écran, « Remboursé par : espèces », mais l'encaissement de l'avoir échoue (simulé).
    Tout ou rien : la réservation et ses billets gardent leurs statuts ; aucun avoir,
    aucune vente AVOIR, aucun règlement négatif ; la ligne reste VALID.
    / The credit note's settlement fails: nothing is cancelled, nothing is written.
    """
    vente_admin = vendre_et_relire(
        lieu, prix="10.00", quantite=2, moyen_de_paiement=PaymentMethod.CC
    )
    reservation = vente_admin.reservation
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    # Une exception dans la vue devient une réponse 500, au lieu de sortir du test.
    # / An exception in the view becomes a 500 response instead of leaving the test.
    client_de_l_admin.raise_request_exception = False
    statut_de_la_reservation_avant = reservation.status
    statuts_des_billets_avant = statuts_des_billets(reservation)

    reponse_de_l_ecran = lancer_l_action_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_RESERVATIONS,
        ACTION_ANNULER_LES_RESERVATIONS,
        [reservation],
    )
    assert "moyen_rembourse" in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)

    with encaissement_qui_echoue():
        confirmer_l_ecran_d_annulation(
            client_de_l_admin,
            URL_DE_LA_LISTE_DES_RESERVATIONS,
            ACTION_ANNULER_LES_RESERVATIONS,
            [reservation],
            moyen_rembourse=PaymentMethod.CASH,
        )

    rien_n_est_annule(
        reservation, statut_de_la_reservation_avant, statuts_des_billets_avant
    )
    rien_n_est_ecrit_pour_la_ligne(vente_admin.ligne)


# --------------------------------------------------------------------------
# Billets vendus à la caisse : la ligne et les billets sur deux tarifs vendus
# / Register tickets: the line and the tickets on two sold prices
# --------------------------------------------------------------------------


def vendre_des_billets_en_especes_a_la_caisse(lieu, acheteur, billetterie, quantite):
    """
    La caisse vend `quantite` billets de l'événement, payés en espèces. Rend la
    réservation créée.
    / The register sells `quantite` tickets of the event, paid in cash. Returns the
    reservation.

    Le geste passe par la vraie route de paiement de la caisse, `POST
    /laboutik/paiement/payer/` (laboutik/views.py, `PaiementViewSet.payer`), comme
    `vendre_un_billet_offert_a_la_caisse` (test_caracterisation_annulations.py) : la clé
    `repid-<événement>__<tarif>` d'une tuile billet porte la quantité, le client est
    identifié par son e-mail. Payer en espèces ne demande pas la carte du gérant.
    La caisse écrit UNE ligne pour le produit, et les billets sur un AUTRE tarif vendu
    (`PriceSold` dont le produit vendu porte l'événement) du même tarif (`Price`).
    / The real register payment route; cash needs no manager card. The register writes
    ONE line, and the tickets on ANOTHER PriceSold of the same Price.

    ÉTAT DE DÉPART, posé ici : la caisse activée EN MÉMOIRE le temps de la vente
    (`configuration_modifiee()`, tests/PIEGES.md 13.22), un point de vente « billetterie »
    caché (tests/PIEGES.md 9.41), un caissier administrateur du lieu connecté.
    / STARTING STATE: register switched on in memory, hidden ticketing point of sale,
    admin cashier.
    """
    point_de_vente_billetterie = PointDeVente.objects.create(
        name=f"TEST_avoirs billetterie {identifiant_unique()}",
        comportement=PointDeVente.BILLETTERIE,
        hidden=True,
    )
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    prix_du_billet_en_centimes = int(round(billetterie.tarif.prix * 100))
    cle_de_la_tuile_billet = (
        f"repid-{billetterie.evenement.uuid}__{billetterie.tarif.uuid}"
    )
    donnees_du_formulaire = {
        "uuid_pv": str(point_de_vente_billetterie.uuid),
        "moyen_paiement": "espece",
        "total": str(prix_du_billet_en_centimes * quantite),
        "given_sum": "0",
        "email_adhesion": acheteur.email,
        cle_de_la_tuile_billet: str(quantite),
    }
    # Le module caisse a besoin du module monnaie locale.
    # / The register module needs the local currency module.
    with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
        reponse_de_la_caisse = client_du_caissier.post(
            "/laboutik/paiement/payer/", donnees_du_formulaire
        )

    assert reponse_de_la_caisse.status_code == 200
    return Reservation.objects.get(user_commande=acheteur, event=billetterie.evenement)


def verifier_la_ligne_et_les_billets_sur_deux_tarifs_vendus(ligne_de_caisse, billets):
    """
    Vérifie l'état de départ d'une vente de caisse : la ligne et les billets ont le
    même tarif (`Price`), mais deux tarifs vendus (`PriceSold`) différents.
    / Checks the register starting state: same Price, two different PriceSold.
    """
    for billet in billets:
        assert billet.pricesold_id != ligne_de_caisse.pricesold_id, (
            "État de départ inattendu : le billet et la ligne de caisse ont le même "
            "tarif vendu."
        )
        assert billet.pricesold.price_id == ligne_de_caisse.pricesold.price_id


def test_annulation_admin_de_tous_les_billets_d_une_reservation_de_caisse_par_l_ecran_billets(
    lieu,
):
    """
    Deux billets à 10 € vendus à la caisse, payés en espèces. Dans la liste des billets,
    l'admin coche LES DEUX billets et lance « Annuler et rembourser » : toute la
    réservation est annulée (`cancel_and_refund_resa`).
    - L'écran trouve la ligne de caisse par le tarif (`Price`), comme l'annulation de la
      réservation : le champ « Remboursé par » est affiché, pré-rempli avec espèces.
    - L'admin valide avec espèces : réservation et billets annulés.
    - L'avoir : quantité −2, net −2000, CREDIT_NOTE ; sa vente AVOIR, liée, réglée ; UN
      règlement espèces −2000.
    / All tickets of a register reservation ticked on the ticket list: the screen finds
    the register line by Price and shows "Refunded by"; one cash credit note of −2000.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    reservation = vendre_des_billets_en_especes_a_la_caisse(
        lieu, acheteur, concert, quantite=2
    )
    ligne_de_caisse = LigneArticle.objects.get(reservation=reservation)
    vente_d_origine = Vente.objects.get(pk=ligne_de_caisse.vente_id)
    tous_les_billets = list(reservation.tickets.order_by("pk"))
    assert len(tous_les_billets) == 2
    verifier_la_ligne_et_les_billets_sur_deux_tarifs_vendus(
        ligne_de_caisse, tous_les_billets
    )
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_ecran = lancer_l_action_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_BILLETS,
        ACTION_ANNULER_LES_BILLETS,
        tous_les_billets,
    )
    assert "moyen_rembourse" in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)
    assert valeur_pre_remplie_du_moyen(reponse_de_l_ecran) == PaymentMethod.CASH

    reponse_de_l_action = confirmer_l_ecran_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_BILLETS,
        ACTION_ANNULER_LES_BILLETS,
        tous_les_billets,
        moyen_rembourse=PaymentMethod.CASH,
    )

    assert reponse_de_l_action.status_code == 302
    reservation.refresh_from_db()
    assert reservation.status == Reservation.CANCELED
    assert statuts_des_billets(reservation) == [Ticket.CANCELED, Ticket.CANCELED]

    avoir = l_avoir_de_la_ligne(ligne_de_caisse)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.qty == Decimal("-2")
    assert avoir.total_ttc == -2000

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.CASH, -2000)
    ]
    verifier_egalites(vente_d_avoir)


def test_annulation_admin_d_un_billet_de_caisse(lieu):
    """
    Deux billets à 10 € vendus à la caisse, payés en espèces. Dans la liste des billets,
    l'admin coche UN seul billet et lance « Annuler et rembourser »
    (`cancel_and_refund_ticket`).
    - L'écran trouve la ligne de caisse par le tarif : champ « Remboursé par »,
      pré-rempli avec espèces.
    - L'admin valide avec espèces : ce billet est annulé, l'autre reste actif, la
      réservation n'est pas annulée.
    - L'avoir d'UNE unité : quantité −1, net −1000 ; sa vente AVOIR, liée, réglée ; UN
      règlement espèces −1000.
    / One register ticket out of two cancelled by the admin: the line is found by Price;
    a one-unit cash credit note of −1000.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    reservation = vendre_des_billets_en_especes_a_la_caisse(
        lieu, acheteur, concert, quantite=2
    )
    ligne_de_caisse = LigneArticle.objects.get(reservation=reservation)
    vente_d_origine = Vente.objects.get(pk=ligne_de_caisse.vente_id)
    billet_a_annuler = reservation.tickets.order_by("pk").first()
    verifier_la_ligne_et_les_billets_sur_deux_tarifs_vendus(
        ligne_de_caisse, [billet_a_annuler]
    )
    statut_de_la_reservation_avant = reservation.status
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_ecran = lancer_l_action_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_BILLETS,
        ACTION_ANNULER_LES_BILLETS,
        [billet_a_annuler],
    )
    assert "moyen_rembourse" in champs_du_formulaire_de_l_ecran(reponse_de_l_ecran)
    assert valeur_pre_remplie_du_moyen(reponse_de_l_ecran) == PaymentMethod.CASH

    reponse_de_l_action = confirmer_l_ecran_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_BILLETS,
        ACTION_ANNULER_LES_BILLETS,
        [billet_a_annuler],
        moyen_rembourse=PaymentMethod.CASH,
    )

    assert reponse_de_l_action.status_code == 302
    billet_a_annuler.refresh_from_db()
    assert billet_a_annuler.status == Ticket.CANCELED
    assert statuts_des_billets(reservation).count(Ticket.CANCELED) == 1
    reservation.refresh_from_db()
    assert reservation.status == statut_de_la_reservation_avant

    avoir = l_avoir_de_la_ligne(ligne_de_caisse)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.qty == Decimal("-1")
    assert avoir.total_ttc == -1000

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.CASH, -1000)
    ]
    verifier_egalites(vente_d_avoir)


def test_annulation_admin_deux_lignes_du_meme_tarif_un_billet_actif(lieu):
    """
    Une réservation dont le même tarif (`Price`) est vendu sur DEUX lignes hors Stripe,
    une unité chacune, à 10 € en espèces. Deux billets ; l'un est déjà annulé par le
    client (sans avoir, D31) : il reste UN billet actif.
    L'admin annule la réservation (`cancel_and_refund_resa`, `annulation_par_l_admin`),
    « Remboursé par : espèces ».
    - Le nombre de billets actifs du tarif DIMINUE de ce qui vient d'être crédité, d'une
      ligne à l'autre : UN seul avoir, d'une unité (−1000), jamais un par ligne.
    - UNE vente AVOIR liée à la vente d'origine ; UN règlement espèces −1000.
    Appel direct du modèle : l'écran n'ajoute rien à cette règle.
    / Two non-Stripe lines of the same Price, one active ticket: the admin cancellation
    writes ONE one-unit credit note (the active count goes down line after line).
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    # ÉTAT DE DÉPART fabriqué directement (tests/PIEGES.md 12.17) : la réservation, ses
    # deux billets (un actif, un annulé par le client) et la vente de ses deux lignes.
    # / STARTING STATE built directly: the reservation, its two tickets (one active, one
    # cancelled by the buyer) and the sale of its two lines.
    produit_vendu_de_l_evenement, _produit_vendu_cree = ProductSold.objects.get_or_create(
        product=concert.produit, event=concert.evenement
    )
    tarif_vendu = PriceSold.objects.create(
        productsold=produit_vendu_de_l_evenement,
        price=concert.tarif,
        prix=concert.tarif.prix,
    )
    reservation = Reservation.objects.create(
        user_commande=acheteur, event=concert.evenement, status=Reservation.VALID
    )
    Ticket.objects.create(
        reservation=reservation, pricesold=tarif_vendu, status=Ticket.NOT_SCANNED
    )
    Ticket.objects.create(
        reservation=reservation, pricesold=tarif_vendu, status=Ticket.CANCELED
    )
    article_d_une_unite_en_especes = {
        "pricesold": tarif_vendu,
        "quantite": Decimal("1"),
        "prix_unitaire": 1000,
        "taux_tva": Decimal("20"),
        "payment_method": PaymentMethod.CASH,
        "reservation": reservation,
        "status": LigneArticle.VALID,
    }
    vente_d_origine = fabriquer_vente_encaissee(
        origine=SaleOrigin.ADMIN,
        articles=[
            dict(article_d_une_unite_en_especes),
            dict(article_d_une_unite_en_especes),
        ],
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 2000}],
    )
    deux_lignes_du_meme_tarif = list(vente_d_origine.articles.all())
    assert len(deux_lignes_du_meme_tarif) == 2

    reservation.cancel_and_refund_resa(
        annulation_par_l_admin=True, moyen_rembourse=PaymentMethod.CASH
    )

    avoirs_des_deux_lignes = LigneArticle.objects.filter(
        credit_note_for__in=deux_lignes_du_meme_tarif
    )
    assert avoirs_des_deux_lignes.count() == 1, (
        f"Un seul billet actif : un seul avoir attendu, "
        f"{avoirs_des_deux_lignes.count()} écrit(s)."
    )
    avoir = avoirs_des_deux_lignes.get()
    assert avoir.qty == Decimal("-1")
    assert avoir.total_ttc == -1000

    ventes_d_avoir = Vente.objects.filter(
        nature=Vente.Nature.AVOIR, vente_liee=vente_d_origine
    )
    assert ventes_d_avoir.count() == 1
    vente_d_avoir = ventes_d_avoir.get()
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.CASH, -1000)
    ]
    verifier_egalites(vente_d_avoir)
    reservation.refresh_from_db()
    assert reservation.status == Reservation.CANCELED


# --------------------------------------------------------------------------
# Annulations par l'utilisateur, achat hors Stripe : aucun avoir (D31)
# / User cancellations of a non-Stripe purchase: no credit note (D31)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("ce_qui_est_annule", ["reservation", "billet"])
def test_annulation_utilisateur_hors_stripe_aucun_avoir_aucune_vente(
    lieu, ce_qui_est_annule
):
    """
    Fiche T9 (D31). Deux billets à 10 € vendus dans l'admin, payés en espèces. Le client
    annule depuis « Mon compte » toute sa réservation, ou un seul billet.
    - AUCUN avoir : aucune ligne d'avoir, aucune vente nouvelle (AVOIR ou autre), aucun
      règlement négatif ; la ligne vendue reste VALID. L'argent reste acquis ; si le lieu
      rembourse, l'admin fait un avoir.
    - Aucun appel à Stripe.
    - Réservation : elle et ses deux billets passent annulés. Billet : ce billet passe
      annulé, l'autre reste actif.
    - Le message dit que l'achat a été réglé sur place et qu'il faut contacter
      l'organisateur pour un éventuel remboursement.
    / D31: a user cancelling a non-Stripe purchase gets no credit note and no sale; only
    the reservation or the ticket is cancelled; the message points to the organiser.
    """
    vente_admin = vendre_et_relire(
        lieu, prix="10.00", quantite=2, moyen_de_paiement=PaymentMethod.CASH
    )
    reservation = vente_admin.reservation
    client_de_l_acheteur = client_de_mon_compte(lieu, vente_admin.acheteur)
    nombre_de_ventes_avant = Vente.objects.count()

    if ce_qui_est_annule == "reservation":
        reponse = annuler_une_reservation_depuis_mon_compte(
            client_de_l_acheteur, reservation
        )
    else:
        billet_a_annuler = reservation.tickets.order_by("pk").first()
        reponse = annuler_un_billet_depuis_mon_compte(
            client_de_l_acheteur, billet_a_annuler
        )

    assert reponse.status_code == 200
    rien_n_est_ecrit_pour_la_ligne(vente_admin.ligne)
    assert Vente.objects.count() == nombre_de_ventes_avant, (
        "Une vente a été écrite par l'annulation de l'utilisateur."
    )
    messages_de_la_personne = " ".join(textes_des_messages_de_l_admin(reponse))
    assert (
        dans_la_langue_du_client(MESSAGE_COMPLEMENTAIRE_REGLE_SUR_PLACE)
        in messages_de_la_personne
    ), (
        messages_de_la_personne
    )
    # Pas de seconde phrase « annulée » : la vue la dit déjà.
    # / No second "cancelled" sentence: the view already says it.
    assert "Votre réservation est annulée" not in messages_de_la_personne
    assert "Votre billet est annulé" not in messages_de_la_personne
    assert lieu.remboursement_stripe.call_count == 0

    reservation.refresh_from_db()
    if ce_qui_est_annule == "reservation":
        assert reservation.status == Reservation.CANCELED
        assert statuts_des_billets(reservation) == [Ticket.CANCELED, Ticket.CANCELED]
    else:
        billet_a_annuler.refresh_from_db()
        assert billet_a_annuler.status == Ticket.CANCELED
        assert statuts_des_billets(reservation).count(Ticket.CANCELED) == 1
        assert reservation.status != Reservation.CANCELED


def test_annulation_utilisateur_booking_hors_stripe_aucun_avoir(lieu):
    """
    D31, booking. Un créneau d'une ressource, payé 12 € en espèces (vente encaissée par
    le service, ligne VALID reliée au booking). La personne annule son booking
    (`cancel_and_refund_booking`, seul appelant : « Mon compte »).
    - AUCUN avoir : aucune ligne d'avoir, aucune vente nouvelle, aucun règlement négatif ;
      la ligne reste VALID.
    - Aucun appel à Stripe.
    - Le booking passe « annulé par l'utilisateur ».
    - Le message dit que l'achat a été réglé sur place et qu'il faut contacter
      l'organisateur pour un éventuel remboursement.
    / D31 for bookings: cancelling a cash-paid booking writes no credit note and no sale;
    the booking is USER_CANCELED; the message points to the organiser.
    """
    location = creer_ressource_avec_tarif(prix="12.00")
    personne = creer_utilisateur()
    # ÉTAT DE DÉPART : un booking déjà payé hors Stripe, fabriqué directement : il pose
    # une vente antérieure, jamais un paiement testé (tests/PIEGES.md 12.17).
    # / STARTING STATE: a booking already paid outside Stripe, built directly.
    booking = Booking.objects.create(
        resource=location.ressource,
        user=personne,
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=1,
        status=Booking.PAID_BY_USER,
    )
    tarif_vendu = creer_tarif_vendu(nom="Créneau", prix_en_euros="12.00")
    vente_du_booking = fabriquer_vente_encaissee(
        origine=SaleOrigin.ADMIN,
        articles=[
            {
                "pricesold": tarif_vendu,
                "quantite": Decimal("1"),
                "prix_unitaire": 1200,
                "taux_tva": Decimal("20"),
                "payment_method": PaymentMethod.CASH,
                "booking": booking,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[{"moyen": PaymentMethod.CASH, "montant": 1200}],
    )
    ligne_du_booking = vente_du_booking.articles.get()
    nombre_de_ventes_avant = Vente.objects.count()

    message_de_l_annulation = booking.cancel_and_refund_booking()

    assert str(message_de_l_annulation) == dans_la_langue_active(
        MESSAGE_BOOKING_REGLE_SUR_PLACE
    )
    rien_n_est_ecrit_pour_la_ligne(ligne_du_booking)
    assert Vente.objects.count() == nombre_de_ventes_avant, (
        "Une vente a été écrite par l'annulation du booking."
    )
    assert lieu.remboursement_stripe.call_count == 0
    booking.refresh_from_db()
    assert booking.status == Booking.USER_CANCELED


def test_annulation_utilisateur_reservation_offerte_garde_le_message_d_avant(lieu):
    """
    D31, cas sans argent : deux billets à 15 € « Offert » vendus dans l'admin (D32 :
    entièrement offerts). Le client annule sa réservation depuis « Mon compte ».
    Aucun argent hors Stripe n'a été payé : le message « Réglé sur place… » ne
    s'affiche PAS, le message d'avant reste. Aucun avoir, réservation annulée.
    / A fully offered reservation cancelled by the user: no "paid on site" message,
    the previous message stays; no credit note.
    """
    vente_admin_offerte = vendre_et_relire(
        lieu, prix="15.00", quantite=2, moyen_de_paiement=PaymentMethod.FREE
    )
    reservation = vente_admin_offerte.reservation
    client_de_l_acheteur = client_de_mon_compte(lieu, vente_admin_offerte.acheteur)

    reponse = annuler_une_reservation_depuis_mon_compte(client_de_l_acheteur, reservation)

    assert reponse.status_code == 200
    messages_de_la_personne = " ".join(textes_des_messages_de_l_admin(reponse))
    # Aucune phrase « réglé(e) sur place ». / No "paid on site" sentence.
    for phrase_regle_sur_place in [
        MESSAGE_COMPLEMENTAIRE_REGLE_SUR_PLACE,
        MESSAGE_BOOKING_REGLE_SUR_PLACE,
    ]:
        assert (
            dans_la_langue_du_client(phrase_regle_sur_place)
            not in messages_de_la_personne
        ), messages_de_la_personne
    rien_n_est_ecrit_pour_la_ligne(vente_admin_offerte.ligne)
    reservation.refresh_from_db()
    assert reservation.status == Reservation.CANCELED


def test_annulation_admin_apres_annulation_utilisateur_d_un_billet_rembourse_le_billet_actif_seulement(
    lieu,
):
    """
    Deux billets à 10 € vendus dans l'admin, payés en espèces. Le client annule UN
    billet depuis « Mon compte » : aucun avoir (D31), l'argent reste acquis. Puis
    l'admin annule la réservation, « Remboursé par : espèces ».
    L'admin ne rembourse que les billets ENCORE ACTIFS, comme le chemin Stripe : un
    avoir d'UNE unité (−1000), un règlement espèces −1000. La réservation est annulée.
    / The user cancels one of two cash tickets (no credit note, D31); the admin then
    cancels the reservation: only the still active ticket is refunded (one unit).
    """
    vente_admin = vendre_et_relire(
        lieu, prix="10.00", quantite=2, moyen_de_paiement=PaymentMethod.CASH
    )
    reservation = vente_admin.reservation
    ligne_d_origine = vente_admin.ligne
    vente_d_origine = Vente.objects.get(pk=ligne_d_origine.vente_id)
    client_de_l_acheteur = client_de_mon_compte(lieu, vente_admin.acheteur)
    billet_annule_par_l_utilisateur = reservation.tickets.order_by("pk").first()
    annuler_un_billet_depuis_mon_compte(
        client_de_l_acheteur, billet_annule_par_l_utilisateur
    )
    billet_annule_par_l_utilisateur.refresh_from_db()
    assert billet_annule_par_l_utilisateur.status == Ticket.CANCELED
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    lancer_l_action_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_RESERVATIONS,
        ACTION_ANNULER_LES_RESERVATIONS,
        [reservation],
    )
    reponse_de_l_action = confirmer_l_ecran_d_annulation(
        client_de_l_admin,
        URL_DE_LA_LISTE_DES_RESERVATIONS,
        ACTION_ANNULER_LES_RESERVATIONS,
        [reservation],
        moyen_rembourse=PaymentMethod.CASH,
    )

    assert reponse_de_l_action.status_code == 302
    reservation.refresh_from_db()
    assert reservation.status == Reservation.CANCELED

    avoir = l_avoir_de_la_ligne(ligne_d_origine)
    assert avoir.qty == Decimal("-1")
    assert avoir.total_ttc == -1000
    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.CASH, -1000)
    ]
    verifier_egalites(vente_d_avoir)


def test_annulation_utilisateur_booking_offert_garde_le_message_d_avant(lieu):
    """
    D31, booking sans argent : un créneau d'une ressource à 12 €, entièrement offert
    (moyen « offert », vente encaissée par le service). La personne annule son booking.
    Aucun argent hors Stripe n'a été payé : le message « réglée sur place » ne
    s'affiche PAS, le message d'avant reste. Aucun avoir ; booking annulé.
    / A fully offered booking cancelled by the user: no "paid on site" message, the
    previous message stays; no credit note.
    """
    location = creer_ressource_avec_tarif(prix="12.00")
    personne = creer_utilisateur()
    # ÉTAT DE DÉPART : un booking offert, fabriqué directement (tests/PIEGES.md 12.17).
    # / STARTING STATE: an offered booking, built directly.
    booking = Booking.objects.create(
        resource=location.ressource,
        user=personne,
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=1,
        status=Booking.PAID_BY_USER,
    )
    tarif_vendu = creer_tarif_vendu(nom="Créneau offert", prix_en_euros="12.00")
    # Le moyen « offert » déclenche la règle du service : part offerte = total, et un
    # règlement FREE de 1200 écrit par le service lui-même.
    # / The FREE method triggers the service rule: fully offered, FREE payment written.
    vente_du_booking = fabriquer_vente_encaissee(
        origine=SaleOrigin.ADMIN,
        articles=[
            {
                "pricesold": tarif_vendu,
                "quantite": Decimal("1"),
                "prix_unitaire": 1200,
                "taux_tva": Decimal("20"),
                "payment_method": PaymentMethod.FREE,
                "booking": booking,
                "status": LigneArticle.VALID,
            }
        ],
    )
    ligne_du_booking = vente_du_booking.articles.get()
    assert ligne_du_booking.part_offerte == ligne_du_booking.total_catalogue == 1200

    message_de_l_annulation = booking.cancel_and_refund_booking()

    assert dans_la_langue_active(MESSAGE_BOOKING_REGLE_SUR_PLACE) not in str(
        message_de_l_annulation
    ), message_de_l_annulation
    assert str(message_de_l_annulation) == str(booking.cancel_text())
    rien_n_est_ecrit_pour_la_ligne(ligne_du_booking)
    booking.refresh_from_db()
    assert booking.status == Booking.USER_CANCELED


def test_annulation_utilisateur_billet_offert_garde_le_message_d_avant(lieu):
    """
    D31, billet sans argent : deux billets à 15 € « Offert » vendus dans l'admin (D32 :
    entièrement offerts). Le client annule UN billet depuis « Mon compte ».
    Aucun argent hors Stripe n'a été payé : le message « Réglé sur place… » ne
    s'affiche PAS, le message d'avant reste. Aucun avoir ; ce billet est annulé.
    Le billet de caisse payé en argent a son propre test :
    `test_annulation_utilisateur_billet_de_caisse_message_regle_sur_place`.
    / One fully offered admin ticket cancelled by the user: no "paid on site" message,
    the previous message stays; no credit note.
    """
    vente_admin_offerte = vendre_et_relire(
        lieu, prix="15.00", quantite=2, moyen_de_paiement=PaymentMethod.FREE
    )
    reservation = vente_admin_offerte.reservation
    billet_a_annuler = reservation.tickets.order_by("pk").first()
    client_de_l_acheteur = client_de_mon_compte(lieu, vente_admin_offerte.acheteur)

    reponse = annuler_un_billet_depuis_mon_compte(client_de_l_acheteur, billet_a_annuler)

    assert reponse.status_code == 200
    messages_de_la_personne = " ".join(textes_des_messages_de_l_admin(reponse))
    # Aucune phrase « réglé sur place ». / No "paid on site" sentence.
    assert (
        dans_la_langue_du_client(MESSAGE_COMPLEMENTAIRE_REGLE_SUR_PLACE)
        not in messages_de_la_personne
    ), messages_de_la_personne
    rien_n_est_ecrit_pour_la_ligne(vente_admin_offerte.ligne)
    billet_a_annuler.refresh_from_db()
    assert billet_a_annuler.status == Ticket.CANCELED


def test_annulation_utilisateur_billet_de_caisse_message_regle_sur_place(lieu):
    """
    D31, billet de caisse : deux billets à 10 € vendus à la caisse, payés en espèces. Le
    client annule UN billet depuis « Mon compte ».
    - La ligne de caisse est retrouvée par le tarif (`Price`) : la caisse écrit sa ligne
      et ses billets sur deux tarifs vendus différents.
    - AUCUN avoir : aucune ligne d'avoir, aucune vente nouvelle ; la ligne reste VALID.
    - Le message dit que l'achat a été réglé sur place et qu'il faut contacter
      l'organisateur pour un éventuel remboursement.
    - Ce billet est annulé, l'autre reste actif.
    / D31 for a register ticket paid in cash: the line is found by Price; no credit note,
    the "paid on site" message; the ticket is cancelled.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    reservation = vendre_des_billets_en_especes_a_la_caisse(
        lieu, acheteur, concert, quantite=2
    )
    ligne_de_caisse = LigneArticle.objects.get(reservation=reservation)
    billet_a_annuler = reservation.tickets.order_by("pk").first()
    verifier_la_ligne_et_les_billets_sur_deux_tarifs_vendus(
        ligne_de_caisse, [billet_a_annuler]
    )
    client_de_l_acheteur = client_de_mon_compte(lieu, acheteur)
    nombre_de_ventes_avant = Vente.objects.count()

    reponse = annuler_un_billet_depuis_mon_compte(client_de_l_acheteur, billet_a_annuler)

    assert reponse.status_code == 200
    messages_de_la_personne = " ".join(textes_des_messages_de_l_admin(reponse))
    assert (
        dans_la_langue_du_client(MESSAGE_COMPLEMENTAIRE_REGLE_SUR_PLACE)
        in messages_de_la_personne
    ), messages_de_la_personne
    rien_n_est_ecrit_pour_la_ligne(ligne_de_caisse)
    assert Vente.objects.count() == nombre_de_ventes_avant, (
        "Une vente a été écrite par l'annulation de l'utilisateur."
    )
    assert lieu.remboursement_stripe.call_count == 0
    billet_a_annuler.refresh_from_db()
    assert billet_a_annuler.status == Ticket.CANCELED
    assert statuts_des_billets(reservation).count(Ticket.CANCELED) == 1


# --------------------------------------------------------------------------
# Annulation d'adhésion par l'admin : un seul avoir, sur le dernier paiement (D30)
# / Admin membership cancellation: one credit note, on the latest payment (D30)
# --------------------------------------------------------------------------

# Le message de fin d'une annulation d'adhésion avec avoir (msgid français existant).
# / The closing message of a membership cancellation with credit note.
MESSAGE_ADHESION_ANNULEE_AVEC_AVOIRS = "Adhésion annulée. %(count)d avoir(s) créé(s)."

# La phrase du formulaire quand le dernier paiement a déjà un avoir (msgid français).
# / The form sentence when the latest payment is already credited (French msgid).
MESSAGE_DERNIER_PAIEMENT_DEJA_REMBOURSE = (
    "Le dernier paiement est déjà remboursé : aucun avoir ne sera créé."
)

# Les repères du formulaire d'annulation d'adhésion (cancel_form.html).
# / Markers of the membership cancellation form.
REPERE_BOUTON_AVEC_AVOIR = 'data-testid="membership-cancel-with-credit-note"'
REPERE_LIGNE_PAYEE_AFFICHEE = 'data-testid="membership-cancel-ligne-payee"'

# L'erreur du formulaire quand le moyen « Remboursé par » manque (msgid français).
# / The form error when the "Refunded by" method is missing (French msgid).
MESSAGE_MOYEN_REMBOURSE_MANQUANT = "Choisissez le moyen par lequel l'argent est rendu."


def message_de_fin_attendu(nombre_d_avoirs):
    """Le message de fin d'une annulation d'adhésion avec avoir, tel que le client le lit.
    / The closing message, as the test client reads it."""
    return dans_la_langue_du_client(MESSAGE_ADHESION_ANNULEE_AVEC_AVOIRS) % {
        "count": nombre_d_avoirs
    }


def url_de_l_annulation_d_adhesion(adhesion):
    """L'adresse du panneau « Annuler l'adhésion » de la fiche adhésion de l'admin.
    / The address of the "Cancel membership" panel of the admin membership page."""
    return f"/memberships/{adhesion.pk}/cancel/"


def ouvrir_le_formulaire_d_annulation_d_adhesion(client_de_l_admin, adhesion):
    """L'admin clique « Annuler l'adhésion » : le formulaire de confirmation s'ouvre
    (GET, partiel HTMX).
    / The admin clicks "Cancel membership": the confirmation form opens (GET)."""
    return client_de_l_admin.get(
        url_de_l_annulation_d_adhesion(adhesion), **EN_TETE_HTMX
    )


def annuler_l_adhesion_avec_avoir(client_de_l_admin, adhesion, moyen_rembourse=None):
    """
    L'admin valide le formulaire par le bouton « Annuler avec avoir »
    (`with_credit_note=1`), avec le moyen « Remboursé par » s'il est donné. Sans moyen,
    le formulaire est envoyé sans ce champ.
    / The admin confirms with "Cancel with credit note", with the "Refunded by" method
    if given.
    """
    donnees_du_formulaire = {"with_credit_note": "1"}
    if moyen_rembourse is not None:
        donnees_du_formulaire["moyen_rembourse"] = moyen_rembourse
    return client_de_l_admin.post(
        url_de_l_annulation_d_adhesion(adhesion),
        donnees_du_formulaire,
        **EN_TETE_HTMX,
    )


class LecteurDuChampRemboursePar(HTMLParser):
    """
    Lit, dans le HTML du formulaire d'annulation d'adhésion, la liste déroulante
    `<select name="moyen_rembourse">` : les moyens proposés (valeurs non vides des
    `<option>`) et le moyen pré-rempli (l'`<option>` marquée `selected`).
    / Reads the `<select name="moyen_rembourse">` of the cancellation form: the offered
    methods and the pre-selected one.
    """

    def __init__(self):
        super().__init__()
        self.champ_present = False
        self.dans_le_champ = False
        self.moyens_proposes = []
        self.moyen_pre_rempli = None

    def handle_starttag(self, balise, attributs):
        attributs_de_la_balise = dict(attributs)
        if balise == "select" and attributs_de_la_balise.get("name") == "moyen_rembourse":
            self.champ_present = True
            self.dans_le_champ = True
            return
        if balise == "option" and self.dans_le_champ:
            valeur_de_l_option = attributs_de_la_balise.get("value") or ""
            if valeur_de_l_option:
                self.moyens_proposes.append(valeur_de_l_option)
            option_selectionnee = "selected" in attributs_de_la_balise
            if option_selectionnee and valeur_de_l_option:
                self.moyen_pre_rempli = valeur_de_l_option

    def handle_endtag(self, balise):
        if balise == "select":
            self.dans_le_champ = False


def lire_le_champ_rembourse_par(reponse_du_formulaire):
    """Lit le champ « Remboursé par » du formulaire d'annulation d'adhésion.
    / Reads the "Refunded by" field of the membership cancellation form."""
    lecteur = LecteurDuChampRemboursePar()
    lecteur.feed(reponse_du_formulaire.content.decode())
    return lecteur


def un_message_contient(reponse, texte_attendu):
    """Dit si l'un des messages laissés à l'admin contient le texte attendu.
    / Tells whether one of the admin messages contains the expected text."""
    for texte_du_message in textes_des_messages_de_l_admin(reponse):
        if texte_attendu in texte_du_message:
            return True
    return False


def l_adhesion_n_est_pas_annulee(adhesion, statut_avant):
    """Vérifie que l'adhésion garde son statut et n'est pas archivée.
    / Checks the membership keeps its status and is not archived."""
    adhesion_relue = Membership.objects.get(pk=adhesion.pk)
    assert adhesion_relue.status == statut_avant, (
        f"L'adhésion a changé de statut : {statut_avant} → {adhesion_relue.status}."
    )
    assert not adhesion_relue.archiver


def adhesion_payee_hors_stripe_dans_l_admin(lieu, moyen_de_paiement):
    """
    ÉTAT DE DÉPART : un administrateur ajoute une adhésion à 20 €, payée au moyen donné,
    par le formulaire « Ajouter une adhésion » (le vrai producteur : vente ADMIN réglée,
    ligne VALID). Rend l'adhésion, l'adhérente, sa ligne et sa vente.
    / STARTING STATE: an admin adds a 20 € membership paid with the given method.
    """
    adhesion_admin = creer_l_adhesion_et_relire(
        lieu, contribution="20", moyen_de_paiement=moyen_de_paiement
    )
    ligne_de_l_adhesion = LigneArticle.objects.get(membership=adhesion_admin.adhesion)
    vente_de_l_adhesion = Vente.objects.get(pk=ligne_de_l_adhesion.vente_id)
    return SimpleNamespace(
        adhesion=adhesion_admin.adhesion,
        adherente=adhesion_admin.adherente,
        ligne=ligne_de_l_adhesion,
        vente=vente_de_l_adhesion,
    )


def test_annulation_adhesion_avoir_seulement_sur_le_dernier_paiement(lieu):
    """
    Annexe T7 (D30). Une adhésion en abonnement payée trois fois par Stripe : l'achat il
    y a deux ans, deux renouvellements il y a un an et hier, 15 € chacun. L'admin
    l'annule avec avoir.
    - UN SEUL avoir : sur la ligne du DERNIER paiement (hier). L'achat et le premier
      renouvellement n'ont aucun avoir et restent VALID.
    - Sa vente AVOIR (origine ADMIN) est réglée, liée à la vente du dernier paiement,
      même client ; UN règlement −1500 au moyen Stripe de ce paiement (`SR`), relié au
      paiement, sans référence externe. Aucun appel à Stripe.
    - Le formulaire ne liste que la ligne du dernier paiement ; le message de fin dit
      « 1 avoir(s) ».
    / T7 (D30): a membership paid three times; cancelled with credit note: ONE credit
    note, on the latest payment only, linked to its sale, one SR payment of −1500.
    """
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00", recurrente=True)
    adhesion_payee_trois_fois = creer_une_adhesion_payee_trois_fois(acheteur, adhesion)
    ligne_de_l_achat, ligne_du_premier_renouvellement, ligne_du_dernier_paiement = (
        adhesion_payee_trois_fois.lignes
    )
    vente_du_dernier_paiement = adhesion_payee_trois_fois.ventes[2]
    paiement_du_dernier_paiement = adhesion_payee_trois_fois.paiements[2]
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    # Le formulaire ne liste que la ligne du dernier paiement, celle de l'avoir.
    # / The form lists the latest payment's line only, the one credited.
    reponse_du_formulaire = ouvrir_le_formulaire_d_annulation_d_adhesion(
        client_de_l_admin, adhesion_payee_trois_fois.adhesion
    )
    assert reponse_du_formulaire.status_code == 200
    contenu_du_formulaire = reponse_du_formulaire.content.decode()
    assert contenu_du_formulaire.count(REPERE_LIGNE_PAYEE_AFFICHEE) == 1
    assert REPERE_BOUTON_AVEC_AVOIR in contenu_du_formulaire

    reponse = annuler_l_adhesion_avec_avoir(
        client_de_l_admin, adhesion_payee_trois_fois.adhesion
    )

    assert reponse.status_code == 204
    adhesion_relue = Membership.objects.get(pk=adhesion_payee_trois_fois.adhesion.pk)
    assert adhesion_relue.status == Membership.ADMIN_CANCELED
    assert lieu.remboursement_stripe.call_count == 0

    # Un seul avoir pour toute l'adhésion. / One credit note for the whole membership.
    avoirs_de_l_adhesion = LigneArticle.objects.filter(
        membership=adhesion_payee_trois_fois.adhesion, credit_note_for__isnull=False
    )
    assert avoirs_de_l_adhesion.count() == 1
    rien_n_est_ecrit_pour_la_ligne(ligne_de_l_achat)
    rien_n_est_ecrit_pour_la_ligne(ligne_du_premier_renouvellement)

    avoir = l_avoir_de_la_ligne(ligne_du_dernier_paiement)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.qty == Decimal("-1")
    assert avoir.amount == 1500
    assert avoir.total_ttc == -1500
    assert avoir.paiement_stripe_id == paiement_du_dernier_paiement.pk

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_du_dernier_paiement,
        client_attendu=vente_du_dernier_paiement.client,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.STRIPE_RECURENT, -1500)
    ]
    reglement_de_l_avoir = vente_d_avoir.reglements.get()
    assert reglement_de_l_avoir.reference_externe == ""
    assert reglement_de_l_avoir.paiement_stripe_id == paiement_du_dernier_paiement.pk

    assert un_message_contient(reponse, message_de_fin_attendu(1))
    verifier_egalites(vente_d_avoir)


def test_annulation_adhesion_avoir_lie(lieu):
    """
    Fiche test 20. Une adhésion à 20 € ajoutée dans l'admin, payée par CB (`CC`).
    - Le formulaire d'annulation propose « Remboursé par » : espèces, CB, chèque,
      virement ; pré-rempli avec CB (le moyen d'origine est dans la liste). L'ouvrir
      n'annule rien.
    - L'admin choisit « espèces » (`CA`) et clique « Annuler avec avoir » : l'adhésion
      passe « annulée par l'admin » ; l'avoir (quantité −1, prix unitaire 2000, net
      −2000, CREDIT_NOTE, relié à l'adhésion) a sa vente AVOIR (origine ADMIN) réglée,
      liée à la vente d'origine, même client, avec UN règlement espèces −2000.
    - Le message de fin dit « 1 avoir(s) ».
    / Test 20. Admin card membership, cancelled with credit note refunded in cash: one
    linked AVOIR sale with one cash payment of −2000.
    """
    adhesion_payee = adhesion_payee_hors_stripe_dans_l_admin(
        lieu, moyen_de_paiement=PaymentMethod.CC
    )
    statut_de_l_adhesion_avant = adhesion_payee.adhesion.status
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_du_formulaire = ouvrir_le_formulaire_d_annulation_d_adhesion(
        client_de_l_admin, adhesion_payee.adhesion
    )
    assert reponse_du_formulaire.status_code == 200
    champ_rembourse_par = lire_le_champ_rembourse_par(reponse_du_formulaire)
    assert champ_rembourse_par.champ_present, (
        "Le formulaire d'annulation n'a pas de champ « Remboursé par » "
        "(<select name=\"moyen_rembourse\">)."
    )
    assert sorted(champ_rembourse_par.moyens_proposes) == sorted(
        MOYENS_DU_CHAMP_REMBOURSE_PAR
    )
    assert champ_rembourse_par.moyen_pre_rempli == PaymentMethod.CC
    # Ouvrir le formulaire n'annule rien. / Opening the form cancels nothing.
    l_adhesion_n_est_pas_annulee(adhesion_payee.adhesion, statut_de_l_adhesion_avant)
    rien_n_est_ecrit_pour_la_ligne(adhesion_payee.ligne)

    reponse = annuler_l_adhesion_avec_avoir(
        client_de_l_admin, adhesion_payee.adhesion, moyen_rembourse=PaymentMethod.CASH
    )

    assert reponse.status_code == 204
    adhesion_relue = Membership.objects.get(pk=adhesion_payee.adhesion.pk)
    assert adhesion_relue.status == Membership.ADMIN_CANCELED

    avoir = l_avoir_de_la_ligne(adhesion_payee.ligne)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.qty == Decimal("-1")
    assert avoir.amount == 2000
    assert avoir.total_ttc == -2000
    assert avoir.membership_id == adhesion_payee.adhesion.pk

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=adhesion_payee.vente,
        client_attendu=adhesion_payee.vente.client,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.CASH, -2000)
    ]
    assert un_message_contient(reponse, message_de_fin_attendu(1))
    verifier_egalites(vente_d_avoir)


def test_annulation_adhesion_sans_moyen_refusee_rien_n_est_annule(lieu):
    """
    Une adhésion à 20 € ajoutée dans l'admin, payée par CB. L'admin clique « Annuler
    avec avoir » SANS choisir de moyen « Remboursé par » (champ absent, puis vide) :
    le formulaire revient (200) avec son champ et l'erreur « Choisissez le moyen par
    lequel l'argent est rendu. », et RIEN n'est annulé : l'adhésion garde
    son statut, aucun avoir, aucune vente AVOIR, aucun règlement ; la ligne reste VALID.
    / "Cancel with credit note" without a "Refunded by" method: the form comes back,
    nothing is cancelled, nothing is written.
    """
    adhesion_payee = adhesion_payee_hors_stripe_dans_l_admin(
        lieu, moyen_de_paiement=PaymentMethod.CC
    )
    statut_de_l_adhesion_avant = adhesion_payee.adhesion.status
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    for moyen_envoye in [None, ""]:
        reponse = annuler_l_adhesion_avec_avoir(
            client_de_l_admin, adhesion_payee.adhesion, moyen_rembourse=moyen_envoye
        )

        assert reponse.status_code == 200, (
            f"Moyen {moyen_envoye!r} : le formulaire doit revenir (200), reçu "
            f"{reponse.status_code}."
        )
        contenu_de_la_reponse = reponse.content.decode()
        assert 'data-testid="membership-cancel-form"' in contenu_de_la_reponse
        assert lire_le_champ_rembourse_par(reponse).champ_present
        # L'erreur vient du formulaire (le moyen manque), pas d'un refus plus loin.
        # Le gabarit échappe l'apostrophe : on compare au texte échappé.
        # / The error comes from the form (missing method); the template escapes it.
        assert (
            escape(dans_la_langue_du_client(MESSAGE_MOYEN_REMBOURSE_MANQUANT))
            in contenu_de_la_reponse
        )
        l_adhesion_n_est_pas_annulee(
            adhesion_payee.adhesion, statut_de_l_adhesion_avant
        )
        rien_n_est_ecrit_pour_la_ligne(adhesion_payee.ligne)


def test_annulation_adhesion_ligne_stripe_n_appelle_pas_stripe(lieu):
    """
    Annexe T8 (D27). Une adhésion à 15 € payée en ligne par Stripe.
    - Le formulaire d'annulation n'a PAS de champ « Remboursé par » et prévient :
      « Remboursez cette somme depuis votre tableau de bord Stripe. ».
    - L'admin clique « Annuler avec avoir » : l'adhésion est annulée ; `stripe.Refund.create`
      n'est JAMAIS appelé ; la vente AVOIR, liée à la vente du paiement, même client, a
      UN règlement −1500 au moyen Stripe d'origine (`Paiement_stripe.moyen`), relié au
      paiement, sans référence externe.
    - Le message de fin redit « Remboursez cette somme depuis votre tableau de bord
      Stripe. ».
    / T8 (D27): Stripe-paid membership: no "Refunded by" field, a warning, no Stripe call,
    one payment at the original Stripe method; the closing message repeats the warning.
    """
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00")
    achat = acheter_une_adhesion_payee_par_stripe(acheteur, adhesion)
    ligne_d_origine = LigneArticle.objects.get(paiement_stripe=achat.paiement)
    vente_d_origine = Vente.objects.get(pk=ligne_d_origine.vente_id)
    achat.paiement.refresh_from_db()
    moyen_stripe_d_origine = achat.paiement.moyen
    assert moyen_stripe_d_origine, "Le paiement Stripe d'origine n'a pas de moyen."
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_du_formulaire = ouvrir_le_formulaire_d_annulation_d_adhesion(
        client_de_l_admin, achat.adhesion
    )
    assert reponse_du_formulaire.status_code == 200
    assert not lire_le_champ_rembourse_par(reponse_du_formulaire).champ_present
    assert (
        dans_la_langue_du_client(MESSAGE_REMBOURSEMENT_STRIPE_A_LA_MAIN)
        in reponse_du_formulaire.content.decode()
    )

    reponse = annuler_l_adhesion_avec_avoir(client_de_l_admin, achat.adhesion)

    assert reponse.status_code == 204
    assert lieu.remboursement_stripe.call_count == 0
    adhesion_relue = Membership.objects.get(pk=achat.adhesion.pk)
    assert adhesion_relue.status == Membership.ADMIN_CANCELED
    assert un_message_contient(
        reponse, dans_la_langue_du_client(MESSAGE_REMBOURSEMENT_STRIPE_A_LA_MAIN)
    )

    avoir = l_avoir_de_la_ligne(ligne_d_origine)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.qty == Decimal("-1")
    assert avoir.amount == 1500
    assert avoir.paiement_stripe_id == achat.paiement.pk

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (moyen_stripe_d_origine, -1500)
    ]
    reglement_de_l_avoir = vente_d_avoir.reglements.get()
    assert reglement_de_l_avoir.reference_externe == ""
    assert reglement_de_l_avoir.paiement_stripe_id == achat.paiement.pk
    verifier_egalites(vente_d_avoir)


def test_annulation_adhesion_dernier_paiement_deja_rembourse_aucun_avoir(lieu):
    """
    D30, pas de remontée. Une adhésion en abonnement payée trois fois par Stripe ; son
    DERNIER paiement a déjà un avoir (émis avant, état de départ écrit par le service).
    - Le formulaire ne propose ni « Annuler avec avoir » ni « Remboursé par », ne liste
      aucune ligne, et dit « Le dernier paiement est déjà remboursé : aucun avoir ne
      sera créé. ».
    - L'admin poste quand même « avec avoir » : AUCUN nouvel avoir, on ne remonte pas à
      la période précédente. L'achat et le
      premier renouvellement n'ont aucun avoir et restent VALID ; le dernier paiement
      garde son seul avoir d'avant.
    - L'adhésion est annulée ; aucun appel à Stripe ; le message de fin dit
      « 0 avoir(s) ».
    / D30, no walking back: the latest payment already has a credit note; cancelling
    with credit note writes NO new one; the earlier payments are untouched.
    """
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00", recurrente=True)
    adhesion_payee_trois_fois = creer_une_adhesion_payee_trois_fois(acheteur, adhesion)
    ligne_de_l_achat, ligne_du_premier_renouvellement, ligne_du_dernier_paiement = (
        adhesion_payee_trois_fois.lignes
    )
    # ÉTAT DE DÉPART : l'avoir déjà émis sur le dernier paiement, par le service.
    # / STARTING STATE: the credit note already issued on the latest payment.
    avoir_deja_emis = services_vente.ecrire_la_vente_d_avoir_d_une_ligne(
        ligne_du_dernier_paiement,
        quantite=Decimal("1"),
        moyen_rembourse=None,
        origine=SaleOrigin.ADMIN,
    )
    nombre_de_ventes_avoir_avant = Vente.objects.filter(
        nature=Vente.Nature.AVOIR
    ).count()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_du_formulaire = ouvrir_le_formulaire_d_annulation_d_adhesion(
        client_de_l_admin, adhesion_payee_trois_fois.adhesion
    )
    assert reponse_du_formulaire.status_code == 200
    contenu_du_formulaire = reponse_du_formulaire.content.decode()
    assert REPERE_BOUTON_AVEC_AVOIR not in contenu_du_formulaire
    assert not lire_le_champ_rembourse_par(reponse_du_formulaire).champ_present
    assert REPERE_LIGNE_PAYEE_AFFICHEE not in contenu_du_formulaire
    assert (
        dans_la_langue_du_client(MESSAGE_DERNIER_PAIEMENT_DEJA_REMBOURSE)
        in contenu_du_formulaire
    )

    reponse = annuler_l_adhesion_avec_avoir(
        client_de_l_admin, adhesion_payee_trois_fois.adhesion
    )

    assert reponse.status_code == 204
    adhesion_relue = Membership.objects.get(pk=adhesion_payee_trois_fois.adhesion.pk)
    assert adhesion_relue.status == Membership.ADMIN_CANCELED
    assert lieu.remboursement_stripe.call_count == 0

    rien_n_est_ecrit_pour_la_ligne(ligne_de_l_achat)
    rien_n_est_ecrit_pour_la_ligne(ligne_du_premier_renouvellement)
    avoirs_du_dernier_paiement = LigneArticle.objects.filter(
        credit_note_for=ligne_du_dernier_paiement
    )
    assert list(avoirs_du_dernier_paiement) == [avoir_deja_emis]
    assert (
        Vente.objects.filter(nature=Vente.Nature.AVOIR).count()
        == nombre_de_ventes_avoir_avant
    )
    assert un_message_contient(reponse, message_de_fin_attendu(0))


def test_annulation_adhesion_echec_d_encaissement_rien_n_est_annule(lieu):
    """
    Une adhésion à 20 € ajoutée dans l'admin, payée par CB. L'admin l'annule avec avoir,
    « Remboursé par : espèces », mais l'encaissement de l'avoir échoue (simulé). Tout ou
    rien : l'adhésion garde son statut ; aucun avoir, aucune vente AVOIR, aucun
    règlement négatif ; la ligne reste VALID. Peu importe la réponse de la vue.
    / The credit note's settlement fails: the membership is not cancelled, nothing is
    written, whatever the view returns.
    """
    adhesion_payee = adhesion_payee_hors_stripe_dans_l_admin(
        lieu, moyen_de_paiement=PaymentMethod.CC
    )
    statut_de_l_adhesion_avant = adhesion_payee.adhesion.status
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    # Une exception dans la vue devient une réponse 500, au lieu de sortir du test.
    # / An exception in the view becomes a 500 response instead of leaving the test.
    client_de_l_admin.raise_request_exception = False

    with encaissement_qui_echoue():
        annuler_l_adhesion_avec_avoir(
            client_de_l_admin,
            adhesion_payee.adhesion,
            moyen_rembourse=PaymentMethod.CASH,
        )

    l_adhesion_n_est_pas_annulee(adhesion_payee.adhesion, statut_de_l_adhesion_avant)
    rien_n_est_ecrit_pour_la_ligne(adhesion_payee.ligne)


def test_annulation_adhesion_entierement_offerte_reglement_free_sans_champ(lieu):
    """
    Une adhésion à 20 € entièrement OFFERTE (part offerte = total catalogue = 2000), dans
    une vente ADMIN réglée par un règlement FREE 2000. L'état de départ est écrit par le
    service de vente : le formulaire « Ajouter une adhésion » n'écrit une adhésion
    offerte qu'à 0.
    - Le formulaire d'annulation n'a PAS de champ « Remboursé par » : il n'y a pas
      d'argent à rendre.
    - L'admin clique « Annuler avec avoir » : l'adhésion est annulée ; l'avoir a
      catalogue −2000, offert −2000, net 0 ; sa vente AVOIR (origine ADMIN), liée à la
      vente d'origine, a UN seul règlement : FREE −2000. Aucun règlement d'argent.
    / A fully offered 20 € membership: no "Refunded by" field; the credit note has
    catalogue −2000, offered −2000, net 0, and ONE FREE payment of −2000.
    """
    adhesion = creer_adhesion(prix="20.00")
    adherente = creer_utilisateur()
    adhesion_offerte = Membership.objects.create(
        user=adherente,
        price=adhesion.tarif,
        first_name="Ada",
        last_name="Lovelace",
        status=Membership.ADMIN_VALID,
    )
    tarif_vendu = get_or_create_price_sold(adhesion.tarif)
    # ÉTAT DE DÉPART : la vente de l'adhésion offerte, écrite par le service (la règle
    # « offert à montant non nul » écrit le règlement FREE 2000).
    # / STARTING STATE: the offered membership sale, written by the sale service.
    vente_d_origine = services_vente.ouvrir_vente(
        origine=SaleOrigin.ADMIN, nature=Vente.Nature.VENTE, client=adherente
    )
    ligne_offerte = services_vente.ajouter_article(
        vente_d_origine,
        pricesold=tarif_vendu,
        quantite=Decimal("1"),
        prix_unitaire=2000,
        taux_tva=Decimal("0"),
        offert_en_totalite=True,
        membership=adhesion_offerte,
        status=LigneArticle.VALID,
    )
    services_vente.encaisser_vente(vente_d_origine)
    assert ligne_offerte.part_offerte == ligne_offerte.total_catalogue == 2000
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_du_formulaire = ouvrir_le_formulaire_d_annulation_d_adhesion(
        client_de_l_admin, adhesion_offerte
    )
    assert reponse_du_formulaire.status_code == 200
    assert not lire_le_champ_rembourse_par(reponse_du_formulaire).champ_present
    assert REPERE_BOUTON_AVEC_AVOIR in reponse_du_formulaire.content.decode()

    reponse = annuler_l_adhesion_avec_avoir(client_de_l_admin, adhesion_offerte)

    assert reponse.status_code == 204
    adhesion_relue = Membership.objects.get(pk=adhesion_offerte.pk)
    assert adhesion_relue.status == Membership.ADMIN_CANCELED

    avoir = l_avoir_de_la_ligne(ligne_offerte)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.qty == Decimal("-1")
    assert avoir.total_catalogue == -2000
    assert avoir.part_offerte == -2000
    assert avoir.total_ttc == 0

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=Vente.objects.get(pk=vente_d_origine.pk),
        client_attendu=adherente,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.FREE, -2000)
    ]
    assert un_message_contient(reponse, message_de_fin_attendu(1))
    verifier_egalites(vente_d_avoir)


def test_annulation_adhesion_payee_en_jetons_reglement_lg_sans_champ(lieu):
    """
    Une adhésion à 20 € payée en jetons cadeau à la caisse (la cascade rattache les
    adhésions à leur part) : une vente ordinaire, net 2000, part payée en jetons 2000
    au taux que la caisse écrit pour ce produit (donc TVA 0), moyen historique LG, avec
    la monnaie des jetons et la carte (D8 bis). L'état de départ est écrit par le
    service de vente.
    - Le formulaire d'annulation n'a PAS de champ « Remboursé par » : une part payée en
      jetons n'a pas d'argent à rendre.
    - L'admin clique « Annuler avec avoir » : l'adhésion est annulée ; l'avoir a
      catalogue −2000, rien d'offert, net −2000 ; sa vente AVOIR (origine ADMIN), liée à
      la vente d'origine, a UN seul règlement : jetons (LG) −2000, avec la monnaie et
      la carte du règlement LG d'origine. Aucun règlement FREE, aucun recrédit de la
      carte.
    / A 20 € membership paid in gift tokens: no "Refunded by" field; the credit note
    has net −2000 and ONE LG payment of −2000 (currency and card copied), no FREE
    payment, no credit back on the card.
    """
    adhesion = creer_adhesion(prix="20.00")
    adherente = creer_utilisateur()
    adhesion_payee_en_jetons = Membership.objects.create(
        user=adherente,
        price=adhesion.tarif,
        first_name="Ada",
        last_name="Lovelace",
        status=Membership.ADMIN_VALID,
    )
    tarif_vendu = get_or_create_price_sold(adhesion.tarif)
    identifiant_de_la_carte = identifiant_unique().upper()
    carte_du_client = CarteCashless.objects.create(
        tag_id=identifiant_de_la_carte,
        number=identifiant_de_la_carte,
        uuid=uuid.uuid4(),
    )
    monnaie_des_jetons = uuid.uuid4()
    # ÉTAT DE DÉPART : la vente de caisse de l'adhésion, payée en jetons.
    # / STARTING STATE: the register sale of the membership, paid in tokens.
    vente_d_origine = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": tarif_vendu,
                "quantite": Decimal("1"),
                "prix_unitaire": 2000,
                "taux_tva": _taux_tva_de_la_ligne_de_caisse(
                    adhesion.tarif.product, PaymentMethod.LOCAL_GIFT
                ),
                "part_en_jetons": 2000,
                "payment_method": PaymentMethod.LOCAL_GIFT,
                "asset": monnaie_des_jetons,
                "carte": carte_du_client,
                "membership": adhesion_payee_en_jetons,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[
            {
                "moyen": PaymentMethod.LOCAL_GIFT,
                "montant": 2000,
                "asset": monnaie_des_jetons,
                "carte": carte_du_client,
            }
        ],
    )
    ligne_payee_en_jetons = vente_d_origine.articles.get()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_du_formulaire = ouvrir_le_formulaire_d_annulation_d_adhesion(
        client_de_l_admin, adhesion_payee_en_jetons
    )
    assert reponse_du_formulaire.status_code == 200
    assert not lire_le_champ_rembourse_par(reponse_du_formulaire).champ_present
    assert REPERE_BOUTON_AVEC_AVOIR in reponse_du_formulaire.content.decode()

    reponse = annuler_l_adhesion_avec_avoir(client_de_l_admin, adhesion_payee_en_jetons)

    assert reponse.status_code == 204
    adhesion_relue = Membership.objects.get(pk=adhesion_payee_en_jetons.pk)
    assert adhesion_relue.status == Membership.ADMIN_CANCELED

    avoir = l_avoir_de_la_ligne(ligne_payee_en_jetons)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.qty == Decimal("-1")
    assert avoir.total_catalogue == -2000
    assert avoir.part_offerte == 0
    assert avoir.total_ttc == -2000

    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.LOCAL_GIFT, -2000)
    ]
    reglement_des_jetons = vente_d_avoir.reglements.get()
    assert reglement_des_jetons.asset == monnaie_des_jetons
    assert reglement_des_jetons.carte_id == carte_du_client.pk
    assert not Transaction.objects.filter(card=carte_du_client).exists()
    assert un_message_contient(reponse, message_de_fin_attendu(1))
    verifier_egalites(vente_d_avoir)


# --------------------------------------------------------------------------
# Demandes simultanées : un billet et un paiement relus sous verrou
# / Simultaneous requests: a ticket and a payment read again under lock
# --------------------------------------------------------------------------


@contextmanager
def requetes_sql_jusqu_a_l_appel_a_stripe():
    """
    Relève le texte SQL des requêtes du bloc (`requetes_sql_relevees`). Remplace
    `stripe.Refund.create` (Stripe rend le montant demandé) et garde, au moment de
    chaque appel, la liste des requêtes déjà faites.
    / Records the block's SQL texts. Replaces `stripe.Refund.create` and keeps, at each
    call, the list of queries already run.

    Une seule connexion ne peut pas faire attendre une seconde demande : on ne voit pas
    un verrou « tenir ». On voit en revanche la requête qui le pose (`FOR UPDATE`) et
    sa place parmi les autres.
    / One connection cannot make a second request wait: we see the locking query and
    its place among the others.

    :return: un objet avec `appels` (le faux `Refund.create`) et
        `requetes_avant_chaque_appel` (une liste de textes SQL par appel à Stripe)
    """
    releve = SimpleNamespace(appels=None, requetes_avant_chaque_appel=[])
    with requetes_sql_relevees() as textes_sql_du_bloc:

        def rembourser_en_relevant_les_requetes(**arguments_du_remboursement):
            requetes_deja_faites = list(textes_sql_du_bloc)
            releve.requetes_avant_chaque_appel.append(requetes_deja_faites)
            return rembourser_comme_stripe(**arguments_du_remboursement)

        with patch(
            "stripe.Refund.create", side_effect=rembourser_en_relevant_les_requetes
        ) as appels_a_stripe:
            releve.appels = appels_a_stripe
            yield releve


def test_annulation_d_un_billet_deja_annule_par_une_autre_demande_refusee(lieu):
    """
    Deux billets à 10 € payés par Stripe. Deux demandes d'annulation du MÊME billet
    arrivent en même temps (deux onglets, ou le client et l'admin) : chacune a chargé la
    réservation et le billet AVANT que l'autre n'écrive.
    - La première annule le billet : Stripe rend 1000, le billet passe annulé.
    - La seconde a encore en mémoire un billet actif. Elle relit le billet sous verrou :
      il est annulé, elle est refusée (« This ticket has already been canceled. »),
      AVANT Stripe.
    - Stripe n'est appelé qu'UNE fois ; un seul remboursement est écrit ; l'autre billet
      reste actif, la réservation n'est pas annulée.
    - La première demande pose le verrou du billet (`SELECT … FOR UPDATE`) AVANT Stripe :
      c'est lui qui fait attendre une demande simultanée (une seule connexion ne peut pas
      le montrer « tenir », on vérifie la requête SQL).
    / Two cancellations of the SAME ticket, both loaded before the other one writes: the
    second reads the ticket again under lock, finds it cancelled and is refused before
    Stripe. One Stripe call, one refund written. The ticket lock is set before Stripe.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=2)
    billets_dans_l_ordre = list(
        Reservation.objects.get(pk=achat.reservation.pk).tickets.order_by("pk")
    )
    billet_vise = billets_dans_l_ordre[0]
    autre_billet = billets_dans_l_ordre[1]

    # Les deux demandes chargent leurs objets avant toute écriture.
    # / Both requests load their objects before any write.
    reservation_lue_par_la_premiere_demande = Reservation.objects.get(
        pk=achat.reservation.pk
    )
    billet_lu_par_la_premiere_demande = Ticket.objects.get(pk=billet_vise.pk)
    reservation_lue_par_la_seconde_demande = Reservation.objects.get(
        pk=achat.reservation.pk
    )
    billet_lu_par_la_seconde_demande = Ticket.objects.get(pk=billet_vise.pk)

    with requetes_sql_jusqu_a_l_appel_a_stripe() as releve_de_la_premiere_demande:
        reservation_lue_par_la_premiere_demande.cancel_and_refund_ticket(
            billet_lu_par_la_premiere_demande
        )
    with remboursement_stripe_simule() as stripe_simule_pour_la_seconde_demande:
        with pytest.raises(Exception) as refus_de_la_seconde_demande:
            reservation_lue_par_la_seconde_demande.cancel_and_refund_ticket(
                billet_lu_par_la_seconde_demande
            )

    assert str(refus_de_la_seconde_demande.value) == dans_la_langue_active(
        "This ticket has already been canceled."
    )
    assert releve_de_la_premiere_demande.appels.call_count == 1
    assert stripe_simule_pour_la_seconde_demande.appels.call_count == 0, (
        "Stripe a été appelé deux fois pour le même billet."
    )

    # La première demande verrouille le billet AVANT d'appeler Stripe : une seconde
    # demande simultanée attend, puis relit le billet annulé.
    # / The first request locks the ticket BEFORE calling Stripe.
    requetes_avant_stripe = releve_de_la_premiere_demande.requetes_avant_chaque_appel[0]
    position_du_verrou_sur_le_billet = position_de_la_premiere_requete(
        requetes_avant_stripe, ['FROM "BaseBillet_ticket"', "FOR UPDATE"]
    )
    assert position_du_verrou_sur_le_billet is not None, (
        "Le billet n'est pas verrouillé (SELECT … FOR UPDATE) avant Stripe."
    )
    assert (
        LigneArticle.objects.filter(paiement_stripe=achat.paiement, qty__lt=0).count()
        == 1
    )
    assert (
        Reglement.objects.filter(paiement_stripe=achat.paiement, montant__lt=0).count()
        == 1
    )

    billet_vise.refresh_from_db()
    autre_billet.refresh_from_db()
    assert billet_vise.status == Ticket.CANCELED
    assert autre_billet.status == Ticket.NOT_SCANNED
    reservation_relue = Reservation.objects.get(pk=achat.reservation.pk)
    assert reservation_relue.status != Reservation.CANCELED


def test_annulation_d_une_reservation_deja_annulee_par_une_autre_demande_refusee(lieu):
    """
    Deux billets à 10 € payés par Stripe. Deux demandes d'annulation de TOUTE la
    réservation arrivent en même temps : chacune a chargé la réservation AVANT que
    l'autre n'écrive.
    - La première annule la réservation : Stripe rend 2000.
    - La seconde a encore en mémoire une réservation payée. Elle relit la réservation
      sous verrou : elle est annulée, la seconde est refusée (« This reservation has
      already been canceled. »), AVANT Stripe.
    - La première demande pose le verrou de la réservation (`SELECT … FOR UPDATE`)
      AVANT Stripe (une seule connexion ne peut pas le montrer « tenir », on vérifie la
      requête SQL).
    / Two cancellations of the whole reservation, both loaded before the other one
    writes: the second reads the reservation again under lock and is refused before
    Stripe. The reservation lock is set before Stripe.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=2)

    # Les deux demandes chargent la réservation avant toute écriture.
    # / Both requests load the reservation before any write.
    reservation_lue_par_la_premiere_demande = Reservation.objects.get(
        pk=achat.reservation.pk
    )
    reservation_lue_par_la_seconde_demande = Reservation.objects.get(
        pk=achat.reservation.pk
    )

    with requetes_sql_jusqu_a_l_appel_a_stripe() as releve_de_la_premiere_demande:
        reservation_lue_par_la_premiere_demande.cancel_and_refund_resa()
    with remboursement_stripe_simule() as stripe_simule_pour_la_seconde_demande:
        with pytest.raises(Exception) as refus_de_la_seconde_demande:
            reservation_lue_par_la_seconde_demande.cancel_and_refund_resa()

    assert str(refus_de_la_seconde_demande.value) == dans_la_langue_active(
        "This reservation has already been canceled."
    )
    assert releve_de_la_premiere_demande.appels.call_count == 1
    assert releve_de_la_premiere_demande.appels.call_args.kwargs["amount"] == 2000
    assert stripe_simule_pour_la_seconde_demande.appels.call_count == 0, (
        "Stripe a été appelé deux fois pour la même réservation."
    )
    assert (
        Reglement.objects.filter(paiement_stripe=achat.paiement, montant__lt=0).count()
        == 1
    )

    requetes_avant_stripe = releve_de_la_premiere_demande.requetes_avant_chaque_appel[0]
    position_du_verrou_sur_la_reservation = position_de_la_premiere_requete(
        requetes_avant_stripe, ['FROM "BaseBillet_reservation"', "FOR UPDATE"]
    )
    assert position_du_verrou_sur_la_reservation is not None, (
        "La réservation n'est pas verrouillée (SELECT … FOR UPDATE) avant Stripe."
    )


def test_remboursement_compte_n_sous_verrou_du_paiement(lieu):
    """
    Trois billets à 10 € payés par Stripe, sur UNE ligne. Deux remboursements d'un
    billet chacun. Le second reçoit un paiement lu AVANT le premier remboursement
    (objet périmé, comme une demande partie en même temps).
    - Le second remboursement verrouille le paiement Stripe (`SELECT … FOR UPDATE`) AVANT
      de compter les règlements négatifs déjà écrits (`n` de la clé d'idempotence) : deux
      demandes du même paiement passent l'une après l'autre.
    - `n` est lu en base, pas sur l'objet périmé : la clé du second vaut
      `remboursement-{paiement}-1`.
    / Two one-ticket refunds; the second gets a payment read before the first refund.
    The payment is locked BEFORE `n` is counted; the key of the second one ends in -1.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=3)
    ligne = LigneArticle.objects.get(paiement_stripe=achat.paiement)
    paiement_lu_avant_le_premier_remboursement = Paiement_stripe.objects.get(
        pk=achat.paiement.pk
    )

    with remboursement_stripe_simule():
        partial_refund_payment(
            Paiement_stripe.objects.get(pk=achat.paiement.pk),
            Configuration.get_solo(),
            [LigneArticle.objects.get(pk=ligne.pk)],
            specified_quantity=1,
        )

    with requetes_sql_jusqu_a_l_appel_a_stripe() as releve:
        partial_refund_payment(
            paiement_lu_avant_le_premier_remboursement,
            Configuration.get_solo(),
            [LigneArticle.objects.get(pk=ligne.pk)],
            specified_quantity=1,
        )

    assert cles_d_idempotence_envoyees(releve.appels) == [
        cle_d_idempotence_attendue(achat.paiement, 1)
    ]

    requetes_avant_stripe = releve.requetes_avant_chaque_appel[0]
    # Le remboursement ne touche qu'un paiement : le seul verrou attendu sur la table
    # des paiements Stripe est le sien.
    # / The refund touches one payment only: the only expected lock on that table.
    position_du_verrou = position_de_la_premiere_requete(
        requetes_avant_stripe, ['FROM "BaseBillet_paiement_stripe"', "FOR UPDATE"]
    )
    position_du_comptage = position_de_la_premiere_requete(
        requetes_avant_stripe, ["COUNT(", 'FROM "BaseBillet_reglement"']
    )
    assert position_du_comptage is not None, (
        "Le comptage des règlements négatifs (n) n'est pas fait avant Stripe."
    )
    assert position_du_verrou is not None, (
        "Le paiement Stripe n'est pas verrouillé (SELECT … FOR UPDATE) avant Stripe."
    )
    assert position_du_verrou < position_du_comptage, (
        "Le paiement Stripe est verrouillé APRÈS le comptage de n."
    )


# --------------------------------------------------------------------------
# L'ancien LaBoutik (V1) : aucun avoir admin, les remboursements Stripe après validation
# / Legacy LaBoutik (V1): no admin credit note, Stripe refunds after commit
# --------------------------------------------------------------------------


def test_avoir_admin_n_est_pas_envoye_a_laboutik(
    lieu, django_capture_on_commit_callbacks
):
    """
    Un billet à 10 € vendu dans l'admin, payé par CB. L'admin émet un avoir (bouton
    « Avoir », remboursé en espèces) : la ligne d'avoir (origine ADMIN) passe
    CREDIT_NOTE, mais AUCUNE tâche `send_refund_to_laboutik` n'est demandée, même après
    la validation de la transaction. Les ventes admin ne partent pas à LaBoutik V1 :
    leurs avoirs non plus (décision du mainteneur, 2026-10-02).
    / An admin credit note (ADMIN origin) turns CREDIT_NOTE but is never sent to
    LaBoutik V1, even after commit.
    """
    vente_admin = vendre_et_relire(
        lieu, prix="10.00", quantite=1, moyen_de_paiement=PaymentMethod.CC
    )
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    # On ne garde que les tâches demandées par l'avoir.
    # / Keep only the tasks requested by the credit note.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse_de_l_action = valider_l_ecran_de_l_avoir(
            client_de_l_admin, vente_admin.ligne, moyen_rembourse=PaymentMethod.CASH
        )

    assert reponse_de_l_action.status_code == 302
    avoir = l_avoir_de_la_ligne(vente_admin.ligne)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    assert avoir.sale_origin == SaleOrigin.ADMIN
    assert "send_refund_to_laboutik" not in noms_des_taches(lieu.taches_demandees)


def test_remboursement_stripe_toujours_envoye_a_laboutik(
    lieu, django_capture_on_commit_callbacks
):
    """
    Deux billets à 10 € payés par Stripe ; le client en annule un
    (`cancel_and_refund_ticket`). Sa vente en ligne est partie à LaBoutik V1 : son
    remboursement y part aussi. UNE tâche `send_refund_to_laboutik` est demandée, pour
    la ligne de remboursement (statut REFUNDED, origine LESPASS).
    / A Stripe refund (REFUNDED, LESPASS) is still sent to LaBoutik V1: one task, for
    the refund line.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=2)
    ligne_d_origine = LigneArticle.objects.get(paiement_stripe=achat.paiement)
    reservation = Reservation.objects.get(pk=achat.reservation.pk)
    billet_a_annuler = reservation.tickets.order_by("pk").first()
    # On ne garde que les tâches demandées par l'annulation.
    # / Keep only the tasks requested by the cancellation.
    lieu.taches_demandees.clear()

    with remboursement_stripe_simule():
        with django_capture_on_commit_callbacks(execute=True):
            reservation.cancel_and_refund_ticket(billet_a_annuler)

    ligne_de_remboursement = le_remboursement_de_la_ligne(ligne_d_origine)
    assert ligne_de_remboursement.status == LigneArticle.REFUNDED
    assert ligne_de_remboursement.sale_origin == SaleOrigin.LESPASS
    assert arguments_des_taches(
        lieu.taches_demandees, "send_refund_to_laboutik"
    ) == [(ligne_de_remboursement.pk,)]


def test_avoir_envoye_a_laboutik_apres_la_transaction(
    lieu, django_capture_on_commit_callbacks
):
    """
    Deux billets à 10 € payés par Stripe ; le client en annule un. L'envoi du
    remboursement à LaBoutik V1 attend la validation de la transaction
    (`transaction.on_commit`) : sinon le worker peut chercher une ligne pas encore
    écrite, ou une ligne qu'un échec a fait disparaître.
    - Pendant la transaction : aucune tâche `send_refund_to_laboutik`.
    - Après la validation : une tâche, pour la ligne de remboursement.
    / The LaBoutik V1 sending waits for the commit: no task during the transaction, one
    task after it.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=2)
    ligne_d_origine = LigneArticle.objects.get(paiement_stripe=achat.paiement)
    reservation = Reservation.objects.get(pk=achat.reservation.pk)
    billet_a_annuler = reservation.tickets.order_by("pk").first()
    lieu.taches_demandees.clear()

    with remboursement_stripe_simule():
        with django_capture_on_commit_callbacks(
            execute=False
        ) as actions_apres_la_validation:
            reservation.cancel_and_refund_ticket(billet_a_annuler)

        taches_pendant_la_transaction = noms_des_taches(lieu.taches_demandees)
        assert "send_refund_to_laboutik" not in taches_pendant_la_transaction, (
            "L'envoi à LaBoutik part avant la validation de la transaction."
        )

        # La transaction est validée : ses actions différées partent.
        # / The transaction is committed: its deferred actions run.
        for action_apres_la_validation in actions_apres_la_validation:
            action_apres_la_validation()

    ligne_de_remboursement = le_remboursement_de_la_ligne(ligne_d_origine)
    assert arguments_des_taches(
        lieu.taches_demandees, "send_refund_to_laboutik"
    ) == [(ligne_de_remboursement.pk,)]


# --------------------------------------------------------------------------
# Deux lignes du même tarif vendu (panier, prix libre)
# / Two lines of the same sold price (cart, free price)
# --------------------------------------------------------------------------


def acheter_au_panier_deux_billets_a_prix_libre_au_meme_montant(
    quantites_saisies=(1, 1),
):
    """
    ÉTAT DE DÉPART : au panier, deux saisies d'un tarif à prix libre, toutes deux à
    12 €, de quantités `quantites_saisies` (1 et 1 par défaut). Le panier fait UNE ligne
    par saisie : deux lignes du MÊME tarif vendu (même `PriceSold`), chacune de la
    quantité saisie. Payé par UN paiement Stripe, puis retour de Stripe : payé.
    / STARTING STATE: two free-price entries typed at 12 € in the cart: two lines of
    the SAME PriceSold, of the typed quantities, one Stripe payment, paid.

    :param quantites_saisies: les quantités des deux saisies (entiers)
    :return: un objet avec `reservation`, `paiement` et `lignes` (les deux lignes, de la
        plus grande quantité à la plus petite)
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="5.00", prix_libre=True)
    panier = PanierSession(requete_avec_session(acheteur))
    for quantite_saisie in quantites_saisies:
        panier.add_ticket(
            concert.evenement.uuid,
            concert.tarif.uuid,
            qty=quantite_saisie,
            custom_amount="12.00",
        )
    commande = payer_le_panier(panier, acheteur)
    paiement = commande.paiement_stripe
    revenir_de_stripe_billetterie(client_connecte(acheteur), paiement)

    lignes_du_paiement = list(
        LigneArticle.objects.filter(paiement_stripe=paiement).order_by("-qty", "pk")
    )
    assert len(lignes_du_paiement) == 2
    assert lignes_du_paiement[0].pricesold_id == lignes_du_paiement[1].pricesold_id, (
        "État de départ : les deux lignes doivent porter le même tarif vendu."
    )
    quantites_des_lignes = sorted(
        [int(lignes_du_paiement[0].qty), int(lignes_du_paiement[1].qty)], reverse=True
    )
    assert quantites_des_lignes == sorted(quantites_saisies, reverse=True)
    for ligne in lignes_du_paiement:
        assert ligne.status in (LigneArticle.VALID, LigneArticle.PAID)

    reservation = commande.reservations.get()
    nombre_de_billets_attendu = sum(quantites_saisies)
    assert (
        reservation.tickets.exclude(status=Ticket.CANCELED).count()
        == nombre_de_billets_attendu
    )
    return SimpleNamespace(
        reservation=reservation, paiement=paiement, lignes=lignes_du_paiement
    )


@pytest.mark.parametrize(
    "geste_d_annulation", ["toute_la_reservation", "billet_par_billet"]
)
def test_annulation_stripe_deux_lignes_du_meme_tarif_vendu(lieu, geste_d_annulation):
    """
    Deux lignes du même tarif vendu (deux billets à prix libre saisis à 12 €), un billet
    chacune, payées par UN paiement Stripe. Le client annule :
    - toute la réservation (`cancel_and_refund_resa`) : les billets actifs du tarif sont
      RÉPARTIS entre les lignes, un par ligne. Stripe est appelé une fois, pour 2400 ;
    - ou les billets l'un après l'autre (`cancel_and_refund_ticket`) : chaque billet est
      rendu sur une ligne qui a ENCORE une quantité à rendre. Stripe est appelé deux
      fois, 1200 chacune.
    Dans les deux cas : chaque ligne a UN remboursement de quantité −1, les deux billets
    sont annulés, le paiement passe « remboursé ».
    / Two lines of the same PriceSold: the whole reservation spreads the tickets between
    the lines; one ticket at a time uses a line that still has something to give back.
    Each line gets ONE refund of −1; both tickets cancelled; payment REFUNDED.
    """
    achat = acheter_au_panier_deux_billets_a_prix_libre_au_meme_montant()
    reservation = Reservation.objects.get(pk=achat.reservation.pk)

    with remboursement_stripe_simule() as stripe_simule:
        if geste_d_annulation == "toute_la_reservation":
            reservation.cancel_and_refund_resa()
        else:
            for billet in list(reservation.tickets.order_by("pk")):
                Reservation.objects.get(pk=reservation.pk).cancel_and_refund_ticket(
                    Ticket.objects.get(pk=billet.pk)
                )

    montants_demandes_a_stripe = []
    for appel in stripe_simule.appels.call_args_list:
        montants_demandes_a_stripe.append(appel.kwargs["amount"])
    if geste_d_annulation == "toute_la_reservation":
        assert montants_demandes_a_stripe == [2400]
    else:
        assert montants_demandes_a_stripe == [1200, 1200]

    for ligne_d_origine in achat.lignes:
        ligne_de_remboursement = le_remboursement_de_la_ligne(ligne_d_origine)
        verifier_l_article_rembourse(
            ligne_de_remboursement, ligne_d_origine, quantite_rendue=1
        )

    for billet in Reservation.objects.get(pk=reservation.pk).tickets.all():
        assert billet.status == Ticket.CANCELED
    paiement_relu = Paiement_stripe.objects.get(pk=achat.paiement.pk)
    assert paiement_relu.status == Paiement_stripe.REFUNDED


def test_annulation_stripe_repartit_les_billets_actifs_entre_les_lignes(lieu):
    """
    Deux lignes du même tarif vendu (prix libre à 12 €), de quantités 2 et 1, payées
    par UN paiement Stripe : trois billets. UN billet est déjà annulé SANS
    remboursement (état posé directement par `update()`, sans signal : PIEGES 12.17).
    L'admin annule toute la réservation (`cancel_and_refund_resa`).
    - Il reste DEUX billets actifs : ils sont répartis entre les lignes, et une ligne
      ne reçoit jamais des billets déjà donnés à la ligne précédente. Deux unités sont
      rendues en tout, pas trois.
    - Stripe est appelé une fois, pour le prix de DEUX billets (2400).
    - Tous les billets sont annulés.
    / Two lines of the same PriceSold (quantities 2 and 1), three tickets, one already
    cancelled without refund: the admin cancellation gives back TWO units in all, and
    Stripe gets the price of two tickets.
    """
    achat = acheter_au_panier_deux_billets_a_prix_libre_au_meme_montant(
        quantites_saisies=(2, 1)
    )
    billet_deja_annule = achat.reservation.tickets.order_by("pk").first()
    Ticket.objects.filter(pk=billet_deja_annule.pk).update(status=Ticket.CANCELED)
    reservation = Reservation.objects.get(pk=achat.reservation.pk)

    with remboursement_stripe_simule() as stripe_simule:
        reservation.cancel_and_refund_resa(annulation_par_l_admin=True)

    assert stripe_simule.appels.call_count == 1
    assert stripe_simule.appels.call_args.kwargs["amount"] == 2400

    quantite_totale_rendue = Decimal("0")
    for ligne_de_remboursement in LigneArticle.objects.filter(
        paiement_stripe=achat.paiement, qty__lt=0
    ):
        quantite_totale_rendue += ligne_de_remboursement.qty
    assert quantite_totale_rendue == Decimal("-2"), (
        f"Deux unités devaient être rendues, {-quantite_totale_rendue} l'ont été."
    )

    for billet in Reservation.objects.get(pk=reservation.pk).tickets.all():
        assert billet.status == Ticket.CANCELED


# --------------------------------------------------------------------------
# Écart « reçu en moins » : Stripe ne rend jamais plus que ce qu'il a encaissé
# / "Received less" gap: Stripe never gives back more than it collected
# --------------------------------------------------------------------------


def test_remboursement_apres_ecart_recu_en_moins_demande_au_plus_l_encaisse(lieu):
    """
    Trois billets (2500 au catalogue), Stripe n'encaisse que 2400 : la vente d'origine a
    un article « Écart d'encaissement — reçu en moins » (−100). Toute la réservation est
    annulée (`cancel_and_refund_resa`).
    - Stripe ne détient que 2400 pour ce paiement : il est appelé UNE fois, pour 2400,
      jamais pour les 2500 des articles (Stripe refuserait).
    - La vente AVOIR a ses deux articles (−2000 et −500), UN règlement de −2400, et un
      article « Écart d'encaissement — reçu en plus » de +100 : il annule l'écart de la
      vente d'origine. Les égalités de la vente tiennent.
    - Le paiement passe « remboursé ».
    / Stripe collected 2400 for 2500 of items: the refund asks Stripe 2400, never 2500;
    the AVOIR sale has its items, one −2400 payment and a +100 gap item.
    """
    achat = reserver_des_billets_a_payer(lieu)
    lieu.stripe.session.amount_total = 2400
    revenir_de_stripe_billetterie(achat.client, achat.paiement)
    paiement = Paiement_stripe.objects.get(pk=achat.paiement.pk)
    assert paiement.montant_encaisse == 2400
    ligne_tarif_plein = LigneArticle.objects.filter(
        paiement_stripe=paiement
    ).order_by("-amount")[0]
    vente_d_origine = Vente.objects.get(pk=ligne_tarif_plein.vente_id)
    reservation = Reservation.objects.get(pk=achat.reservation.pk)

    with remboursement_stripe_simule() as stripe_simule:
        reservation.cancel_and_refund_resa()

    assert stripe_simule.appels.call_count == 1
    assert stripe_simule.appels.call_args.kwargs["amount"] == 2400
    remboursement = stripe_simule.remboursements_rendus[0]

    avoir_tarif_plein = le_remboursement_de_la_ligne(ligne_tarif_plein)
    vente_d_avoir = verifier_la_vente_d_avoir_encaissee(
        avoir_tarif_plein,
        vente_liee_attendue=vente_d_origine,
        client_attendu=vente_d_origine.client,
        origine_attendue=SaleOrigin.LESPASS,
    )
    verifier_le_reglement_stripe_du_remboursement(
        vente_d_avoir, paiement, remboursement
    )
    assert moyens_et_montants_des_reglements(vente_d_avoir)[0][1] == -2400

    articles_d_ecart = articles_d_ecart_de_la_vente(vente_d_avoir)
    assert len(articles_d_ecart) == 1
    verifier_l_article_d_ecart(
        articles_d_ecart[0],
        nom_attendu=NOM_ECART_RECU_EN_PLUS,
        quantite_attendue=1,
        ecart_en_centimes=100,
    )
    verifier_egalites(vente_d_avoir)

    paiement.refresh_from_db()
    assert paiement.status == Paiement_stripe.REFUNDED


# --------------------------------------------------------------------------
# Ligne payée en points ou en temps : aucun avoir
# / Line paid in points or time: no credit note
# --------------------------------------------------------------------------

# Le refus de « Avoir sur un article » pour une vente en points ou en temps (msgid
# français) : une ligne payée en points est dans une vente qui n'est pas en euros.
# / The item credit note refusal for a points or time sale (French msgid).
MESSAGE_LIGNE_PAYEE_EN_POINTS = (
    "Cette vente n'est pas en euros (points ou temps) : l'avoir n'est pas possible."
)

# Le début du refus du service (ValueError, texte non traduit).
# / The start of the service refusal (ValueError, untranslated text).
DEBUT_DU_REFUS_DU_SERVICE_POUR_LES_POINTS = "payée en points ou en temps"

# La phrase du formulaire d'annulation d'une adhésion payée en points (msgid français),
# et son repère.
# / The cancellation form sentence for a membership paid in points, and its marker.
MESSAGE_ADHESION_PAYEE_EN_POINTS = (
    "Adhésion payée en points ou en temps : aucun avoir n'est possible, et les points "
    "ne sont pas rendus sur la carte."
)
REPERE_ADHESION_PAYEE_EN_POINTS = 'data-testid="membership-cancel-payee-en-points"'


def vendre_a_la_caisse_un_article_paye_en_points(adhesion=None):
    """
    ÉTAT DE DÉPART : une vente de caisse en points, comme la caisse l'écrit
    (`laboutik/views.py` `_payer_par_nfc`) : la vente est tenue dans la monnaie de
    points (`unite` = son uuid), un article à 300 centièmes de points, TVA 0, moyen
    historique « points ou temps » (NM), un règlement NM de 300. Si une adhésion est
    donnée, l'article lui est relié (adhésion payée en points). Rend la ligne.
    / STARTING STATE: a register sale in points (unit = the points currency), one item
    of 300 hundredths of points, 0 VAT, NM method, one NM payment.
    """
    monnaie_de_points = uuid.uuid4()
    if adhesion is not None:
        tarif_vendu = get_or_create_price_sold(adhesion.price)
    else:
        tarif_vendu = creer_tarif_vendu(nom="Planche en points", taux_tva="0.00")
    vente_en_points = services_vente.ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.VENTE,
        unite=str(monnaie_de_points),
    )
    ligne_payee_en_points = services_vente.ajouter_article(
        vente_en_points,
        pricesold=tarif_vendu,
        quantite=Decimal("1"),
        prix_unitaire=300,
        taux_tva=Decimal("0"),
        payment_method=PaymentMethod.NON_MONETAIRE,
        asset=monnaie_de_points,
        membership=adhesion,
        status=LigneArticle.VALID,
    )
    services_vente.ajouter_reglement(
        vente_en_points,
        moyen=PaymentMethod.NON_MONETAIRE,
        montant=300,
        asset=monnaie_de_points,
    )
    services_vente.encaisser_vente(vente_en_points)
    return LigneArticle.objects.get(pk=ligne_payee_en_points.pk)


def nombre_de_ventes_avoir():
    """Le nombre de ventes AVOIR du lieu. / The number of AVOIR sales of the venue."""
    return Vente.objects.filter(nature=Vente.Nature.AVOIR).count()


def test_avoir_ligne_payee_en_points_refuse_par_la_fonction_commune(lieu):
    """
    Une planche vendue 300 centièmes de points à la caisse (vente en points, moyen NM).
    Un avoir par la fonction commune des avoirs est refusé (ValueError) : l'avoir est
    une vente en euros, il rendrait de l'argent pour des points. Rien n'est écrit :
    aucune vente AVOIR, aucune ligne d'avoir, la ligne reste VALID.
    / An item sold in points: the common credit note function refuses it, nothing is
    written.
    """
    ligne_payee_en_points = vendre_a_la_caisse_un_article_paye_en_points()
    nombre_de_ventes_avoir_avant = nombre_de_ventes_avoir()

    with pytest.raises(ValueError, match=DEBUT_DU_REFUS_DU_SERVICE_POUR_LES_POINTS):
        services_vente.ecrire_la_vente_d_avoir_d_une_ligne(
            ligne_payee_en_points,
            quantite=Decimal("1"),
            moyen_rembourse=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )

    assert nombre_de_ventes_avoir() == nombre_de_ventes_avoir_avant
    rien_n_est_ecrit_pour_la_ligne(ligne_payee_en_points)


def test_avoir_ligne_payee_en_points_refuse_par_l_article_d_avoir(lieu):
    """
    La garde est dans `ajouter_l_article_d_avoir`, la fonction que partagent tous les
    producteurs d'avoir (bouton « Avoir », annulations, remboursement Stripe) : appelée
    seule sur une vente AVOIR ouverte, elle refuse la ligne en points, et n'ajoute aucun
    article.
    / The guard is in the shared `ajouter_l_article_d_avoir`: called alone, it refuses
    the points line and adds no item.
    """
    ligne_payee_en_points = vendre_a_la_caisse_un_article_paye_en_points()
    vente_d_avoir = services_vente.ouvrir_vente(
        origine=SaleOrigin.ADMIN,
        nature=Vente.Nature.AVOIR,
        vente_liee=ligne_payee_en_points.vente,
    )

    with pytest.raises(ValueError, match=DEBUT_DU_REFUS_DU_SERVICE_POUR_LES_POINTS):
        services_vente.ajouter_l_article_d_avoir(
            vente_d_avoir, ligne_payee_en_points, Decimal("1")
        )

    assert not LigneArticle.objects.filter(vente=vente_d_avoir).exists()


def test_avoir_admin_ligne_payee_en_points_l_ecran_ne_s_ouvre_pas(lieu):
    """
    L'admin ouvre « Avoir sur un article » pour la ligne en points (GET) : l'écran ne
    s'ouvre pas, il revient à la fiche de la vente avec le message « Cette vente n'est
    pas en euros (points ou temps) : l'avoir n'est pas possible. ». Rien n'est écrit.
    / The admin clicks "Credit note" on the points line: the screen does not open, a
    message explains why, nothing is written.
    """
    ligne_payee_en_points = vendre_a_la_caisse_un_article_paye_en_points()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_ecran = ouvrir_l_ecran_de_l_avoir(
        client_de_l_admin, ligne_payee_en_points
    )

    assert reponse_de_l_ecran.status_code == 302
    assert dans_la_langue_du_client(
        MESSAGE_LIGNE_PAYEE_EN_POINTS
    ) in textes_des_messages_de_l_admin(reponse_de_l_ecran)
    rien_n_est_ecrit_pour_la_ligne(ligne_payee_en_points)


def test_avoir_admin_ligne_payee_en_points_validation_refusee(lieu):
    """
    L'admin envoie quand même le formulaire (POST, « Remboursé par : espèces ») : refus,
    même message, rien n'est écrit (aucune vente AVOIR, aucun règlement).
    / The admin posts the form anyway: refused, same message, nothing written.
    """
    ligne_payee_en_points = vendre_a_la_caisse_un_article_paye_en_points()
    nombre_de_ventes_avoir_avant = nombre_de_ventes_avoir()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_de_l_action = valider_l_ecran_de_l_avoir(
        client_de_l_admin, ligne_payee_en_points, moyen_rembourse=PaymentMethod.CASH
    )

    assert reponse_de_l_action.status_code == 302
    assert dans_la_langue_du_client(
        MESSAGE_LIGNE_PAYEE_EN_POINTS
    ) in textes_des_messages_de_l_admin(reponse_de_l_action)
    assert nombre_de_ventes_avoir() == nombre_de_ventes_avoir_avant
    rien_n_est_ecrit_pour_la_ligne(ligne_payee_en_points)


def test_avoir_recharge_offerte_en_points_refusee(lieu):
    """
    Une recharge de 500 centièmes de points offerte par l'API v2, comme
    `api_v2/views.py` l'écrit : vente en points, article hors chiffre d'affaires
    entièrement offert, moyen historique FREE (pas NM), règlement FREE. Son avoir est
    refusé : la vente n'est pas en euros. Rien n'est écrit.
    / A points top-up offered by the API v2 (points sale, FREE line): refused, because
    the sale is not in euros.
    """
    monnaie_de_points = uuid.uuid4()
    tarif_de_la_recharge = creer_tarif_vendu(
        nom="Recharge en points",
        prix_en_euros="0.00",
        taux_tva="0.00",
        categorie_article=Product.RECHARGE_CASHLESS,
    )
    vente_de_la_recharge = services_vente.ouvrir_vente(
        origine=SaleOrigin.LESPASS,
        nature=Vente.Nature.VENTE,
        unite=str(monnaie_de_points),
    )
    article_de_la_recharge = services_vente.ajouter_article(
        vente_de_la_recharge,
        pricesold=tarif_de_la_recharge,
        quantite=Decimal("1"),
        prix_unitaire=500,
        taux_tva=Decimal("0"),
        offert_en_totalite=True,
        asset=monnaie_de_points,
        payment_method=PaymentMethod.FREE,
        status=LigneArticle.VALID,
    )
    services_vente.encaisser_vente(vente_de_la_recharge)
    # Relue en base : l'objet rendu par `ajouter_article` garde sa vente « en attente ».
    # / Read back: the object from `ajouter_article` keeps its sale "pending".
    ligne_de_la_recharge = LigneArticle.objects.get(pk=article_de_la_recharge.pk)
    nombre_de_ventes_avoir_avant = nombre_de_ventes_avoir()

    with pytest.raises(ValueError, match=DEBUT_DU_REFUS_DU_SERVICE_POUR_LES_POINTS):
        services_vente.ecrire_la_vente_d_avoir_d_une_ligne(
            ligne_de_la_recharge,
            quantite=Decimal("1"),
            moyen_rembourse=None,
            origine=SaleOrigin.ADMIN,
        )

    assert nombre_de_ventes_avoir() == nombre_de_ventes_avoir_avant
    rien_n_est_ecrit_pour_la_ligne(ligne_de_la_recharge)


def test_avoir_ligne_sans_vente_au_moyen_points_refusee(lieu):
    """
    Une ligne écrite sans vente (avant le chantier), au moyen « points ou temps » (NM) :
    rien ne dit son unité, sauf son moyen. Son avoir est refusé ; aucune vente AVOIR,
    aucune ligne d'avoir.
    / A line without sale, NM method: refused; no AVOIR sale, no credit note line.
    """
    tarif_vendu = creer_tarif_vendu(nom="Ancienne vente en points", taux_tva="0.00")
    # ÉTAT DE DÉPART : une ligne d'avant le chantier, sans vente, par `create()` direct.
    # / STARTING STATE: a pre-chantier line without sale, written by create().
    ligne_sans_vente_en_points = LigneArticle.objects.create(
        pricesold=tarif_vendu,
        qty=1,
        amount=300,
        vat=Decimal("0"),
        payment_method=PaymentMethod.NON_MONETAIRE,
        sale_origin=SaleOrigin.LABOUTIK,
        status=LigneArticle.VALID,
    )
    assert ligne_sans_vente_en_points.vente_id is None
    nombre_de_ventes_avoir_avant = nombre_de_ventes_avoir()

    with pytest.raises(ValueError, match=DEBUT_DU_REFUS_DU_SERVICE_POUR_LES_POINTS):
        services_vente.ecrire_la_vente_d_avoir_d_une_ligne(
            ligne_sans_vente_en_points,
            quantite=Decimal("1"),
            moyen_rembourse=PaymentMethod.CASH,
            origine=SaleOrigin.ADMIN,
        )

    assert nombre_de_ventes_avoir() == nombre_de_ventes_avoir_avant
    rien_n_est_ecrit_pour_la_ligne(ligne_sans_vente_en_points)


def test_avoir_temoin_part_d_une_vente_en_euros_a_plusieurs_moyens_remboursable(lieu):
    """
    Témoin : une bière à 5 € payée en deux parts (jetons cadeau et CB), dans une vente
    en euros. La part payée par CB reste remboursable : son avoir est écrit (CREDIT_NOTE)
    et sa vente AVOIR a UN règlement espèces de −200.
    / Control case: a part of a multi-method euro sale is still refundable.
    """
    biere_en_deux_parts = vendre_a_la_caisse_une_biere_en_deux_parts()
    part_en_carte = biere_en_deux_parts.part_en_carte

    avoir = services_vente.ecrire_la_vente_d_avoir_d_une_ligne(
        part_en_carte,
        quantite=part_en_carte.qty,
        moyen_rembourse=PaymentMethod.CASH,
        origine=SaleOrigin.ADMIN,
    )

    assert avoir.status == LigneArticle.CREDIT_NOTE
    vente_d_avoir = Vente.objects.get(pk=avoir.vente_id)
    assert moyens_et_montants_des_reglements(vente_d_avoir) == [
        (PaymentMethod.CASH, -200)
    ]
    verifier_egalites(vente_d_avoir)


def adhesion_payee_en_points_a_la_caisse():
    """
    ÉTAT DE DÉPART : une adhésion payée 300 centièmes de points à la caisse, comme la
    caisse l'écrit : l'adhésion porte le moyen NM, sa ligne est l'article d'une vente
    en points. Rend l'adhésion et sa ligne.
    / STARTING STATE: a membership paid in points at the register (NM membership, its
    line in a points sale).
    """
    adhesion = creer_adhesion(prix="3.00")
    adherente = creer_utilisateur()
    adhesion_payee_en_points = Membership.objects.create(
        user=adherente,
        price=adhesion.tarif,
        first_name="Ada",
        last_name="Lovelace",
        status=Membership.ADMIN_VALID,
        payment_method=PaymentMethod.NON_MONETAIRE,
    )
    ligne_de_l_adhesion = vendre_a_la_caisse_un_article_paye_en_points(
        adhesion=adhesion_payee_en_points
    )
    return SimpleNamespace(adhesion=adhesion_payee_en_points, ligne=ligne_de_l_adhesion)


def test_annulation_adhesion_payee_en_points_seulement_sans_avoir_et_le_dit(lieu):
    """
    Le formulaire d'annulation d'une adhésion payée en points ne propose que « Annuler
    sans avoir » : ni bouton « Annuler avec avoir », ni champ « Remboursé par », ni
    ligne de paiement à créditer. Il le dit, dans une phrase visible : « Adhésion payée
    en points ou en temps : aucun avoir n'est possible, et les points ne sont pas
    rendus sur la carte. »
    / The form of a points membership only offers "Cancel without credit note", and
    says why in a visible sentence.
    """
    adhesion_en_points = adhesion_payee_en_points_a_la_caisse()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse_du_formulaire = ouvrir_le_formulaire_d_annulation_d_adhesion(
        client_de_l_admin, adhesion_en_points.adhesion
    )

    assert reponse_du_formulaire.status_code == 200
    contenu_du_formulaire = reponse_du_formulaire.content.decode()
    assert REPERE_BOUTON_AVEC_AVOIR not in contenu_du_formulaire
    assert not lire_le_champ_rembourse_par(reponse_du_formulaire).champ_present
    assert REPERE_LIGNE_PAYEE_AFFICHEE not in contenu_du_formulaire
    assert REPERE_ADHESION_PAYEE_EN_POINTS in contenu_du_formulaire
    assert (
        dans_la_langue_du_client(MESSAGE_ADHESION_PAYEE_EN_POINTS)
        in contenu_du_formulaire
    )
    assert dans_la_langue_du_client("Annuler sans avoir") in contenu_du_formulaire


def test_annulation_adhesion_payee_en_points_sans_avoir_fonctionne(lieu):
    """
    L'admin clique « Annuler sans avoir » : l'adhésion est annulée (204), aucun avoir,
    aucune vente AVOIR ; la ligne payée en points reste VALID.
    / "Cancel without credit note": the membership is cancelled, no credit note.
    """
    adhesion_en_points = adhesion_payee_en_points_a_la_caisse()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse = client_de_l_admin.post(
        url_de_l_annulation_d_adhesion(adhesion_en_points.adhesion),
        {"with_credit_note": "0"},
        **EN_TETE_HTMX,
    )

    assert reponse.status_code == 204
    adhesion_relue = Membership.objects.get(pk=adhesion_en_points.adhesion.pk)
    assert adhesion_relue.status == Membership.ADMIN_CANCELED
    rien_n_est_ecrit_pour_la_ligne(adhesion_en_points.ligne)


def test_annulation_adhesion_payee_en_points_avec_avoir_force_refuse(lieu):
    """
    Un POST « Annuler avec avoir » forcé (le bouton n'est pas affiché), avec « Remboursé
    par : espèces » : le formulaire revient (200) avec l'erreur, l'adhésion n'est PAS
    annulée et rien n'est écrit. L'annulation ne se fait jamais en silence sans l'avoir
    demandé.
    / A forced "with credit note" POST: the form comes back with the error, the
    membership is not cancelled, nothing is written.
    """
    adhesion_en_points = adhesion_payee_en_points_a_la_caisse()
    statut_de_l_adhesion_avant = adhesion_en_points.adhesion.status
    nombre_de_ventes_avoir_avant = nombre_de_ventes_avoir()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse = annuler_l_adhesion_avec_avoir(
        client_de_l_admin,
        adhesion_en_points.adhesion,
        moyen_rembourse=PaymentMethod.CASH,
    )

    assert reponse.status_code == 200
    contenu_de_la_reponse = reponse.content.decode()
    assert 'data-testid="membership-cancel-errors"' in contenu_de_la_reponse
    assert (
        escape(dans_la_langue_du_client(MESSAGE_ADHESION_PAYEE_EN_POINTS))
        in contenu_de_la_reponse
    )
    l_adhesion_n_est_pas_annulee(
        adhesion_en_points.adhesion, statut_de_l_adhesion_avant
    )
    assert nombre_de_ventes_avoir() == nombre_de_ventes_avoir_avant
    rien_n_est_ecrit_pour_la_ligne(adhesion_en_points.ligne)


def test_annulation_adhesion_payee_en_points_avec_avoir_force_dit_la_phrase_une_fois(
    lieu,
):
    """
    Un POST « Annuler avec avoir » forcé sur une adhésion payée en points : le
    formulaire revient avec l'erreur. La phrase « Adhésion payée en points ou en
    temps : aucun avoir n'est possible… » n'est écrite qu'UNE fois dans la réponse,
    jamais à la fois dans l'erreur et dans la note du formulaire.
    / A forced "with credit note" POST on a points membership: the sentence appears
    only ONCE in the response, never both in the error and in the form's note.
    """
    adhesion_en_points = adhesion_payee_en_points_a_la_caisse()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)

    reponse = annuler_l_adhesion_avec_avoir(
        client_de_l_admin,
        adhesion_en_points.adhesion,
        moyen_rembourse=PaymentMethod.CASH,
    )

    assert reponse.status_code == 200
    # Le texte est lu sans échappement HTML : l'erreur ({{ }}) échappe l'apostrophe,
    # la note ({% translate %}) ne l'échappe pas. Les deux formes sont comptées.
    # / The text is read unescaped: both the escaped and the raw forms are counted.
    contenu_sans_echappement = unescape(reponse.content.decode())
    phrase_de_l_adhesion_payee_en_points = dans_la_langue_du_client(
        MESSAGE_ADHESION_PAYEE_EN_POINTS
    )
    assert contenu_sans_echappement.count(phrase_de_l_adhesion_payee_en_points) == 1


# --------------------------------------------------------------------------
# Le coût d'achat de l'avoir : le coût figé de la ligne d'origine, en négatif
# / The credit note's purchase cost: the original line's frozen cost, negative
# --------------------------------------------------------------------------


def avoir_de_la_ligne_par_le_service(ligne_d_origine, quantite_rendue):
    """
    L'article d'avoir de `quantite_rendue` unités de la ligne, écrit par
    `ajouter_l_article_d_avoir` dans une vente AVOIR ouverte (pas encaissée : seul
    l'article est regardé).
    / The credit note item written by `ajouter_l_article_d_avoir` in an open AVOIR sale.
    """
    vente_d_avoir = services_vente.ouvrir_vente(
        origine=SaleOrigin.ADMIN,
        nature=Vente.Nature.AVOIR,
        vente_liee=ligne_d_origine.vente,
    )
    return services_vente.ajouter_l_article_d_avoir(
        vente_d_avoir, ligne_d_origine, quantite_rendue
    )


def ligne_d_une_vente_en_especes(article):
    """
    ÉTAT DE DÉPART : une vente de caisse en espèces d'un seul article VALID
    (dictionnaire passé à `ajouter_article`, sans statut), encaissée. Le règlement
    espèces vaut le total catalogue de l'article. Rend la ligne de l'article.
    / STARTING STATE: a settled cash register sale of one VALID item.
    """
    article_valide = dict(article)
    article_valide["status"] = LigneArticle.VALID
    montants_de_l_article = services_vente.calculer_montants_article(
        prix_unitaire=article["prix_unitaire"],
        quantite=article["quantite"],
        taux_tva=article["taux_tva"],
    )
    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[article_valide],
        reglements=[
            {
                "moyen": PaymentMethod.CASH,
                "montant": montants_de_l_article["total_catalogue"],
            }
        ],
    )
    return vente.articles.get()


def test_cout_de_l_avoir_rendu_total_exactement_en_miroir(lieu):
    """
    Un jus 3,50 €, prix d'achat 1,20 € : coût d'origine 120. Tout est rendu : l'avoir
    porte un coût de −120, exactement l'opposé.
    / Full return: the credit note's cost is exactly the opposite (−120).
    """
    ligne_du_jus = ligne_d_une_vente_en_especes(
        {
            "pricesold": creer_tarif_vendu(nom="Jus", prix_en_euros="3.50"),
            "quantite": Decimal("1"),
            "prix_unitaire": 350,
            "taux_tva": Decimal("20"),
            "prix_achat": 120,
        }
    )
    assert ligne_du_jus.cout_achat == 120

    avoir = avoir_de_la_ligne_par_le_service(ligne_du_jus, Decimal("1"))

    assert avoir.cout_achat == -120


def test_cout_de_l_avoir_partiel_au_prorata_arrondi_demi_haut(lieu):
    """
    Deux portions de fromage, coût d'origine figé à 75 (un coût impair, imposé comme
    l'avoir le fait pour un coût déjà figé). Une portion est rendue : coût de l'avoir =
    arrondi_demi_haut(75 × −1 / 2) = arrondi(−37,5) = −38 (0,5 s'éloigne de zéro).
    / Partial return: prorata of the frozen cost, rounded half up (−37.5 → −38).
    """
    ligne_du_fromage = ligne_d_une_vente_en_especes(
        {
            "pricesold": creer_tarif_vendu(nom="Fromage", prix_en_euros="2.50"),
            "quantite": Decimal("2"),
            "prix_unitaire": 250,
            "taux_tva": Decimal("5.5"),
            "prix_achat": 300,
            "cout_achat_impose": 75,
        }
    )
    assert ligne_du_fromage.cout_achat == 75

    avoir = avoir_de_la_ligne_par_le_service(ligne_du_fromage, Decimal("1"))

    assert avoir.cout_achat == -38


def test_cout_de_l_avoir_article_au_poids_reprend_le_poids_servi(lieu):
    """
    Un fromage au poids comme la caisse l'écrit (D15) : 0,350 kg au prix du kilo
    (12,90 €), coût sur le poids servi (0,350 kg × 8,00 € = 280). L'article entier est
    rendu : l'avoir rend −280, jamais le prix d'achat au kilo multiplié par une
    quantité d'une pièce (−800).
    / A weight item (D15): the credit note gives back −280 (the served weight's cost).
    """
    ligne_du_fromage = ligne_d_une_vente_en_especes(
        {
            "pricesold": creer_tarif_vendu(nom="Fromage au poids", prix_en_euros="12.90"),
            "quantite": Decimal("0.350"),
            "prix_unitaire": 1290,
            "taux_tva": Decimal("5.5"),
            "prix_achat": 800,
            "weight_quantity": 350,
        }
    )
    assert ligne_du_fromage.cout_achat == 280

    avoir = avoir_de_la_ligne_par_le_service(ligne_du_fromage, Decimal("0.350"))

    assert avoir.cout_achat == -280


def test_cout_de_l_avoir_part_de_cascade(lieu):
    """
    Une bière payée en deux parts (jetons 0,6, CB 0,4), prix d'achat 1,25 € : la part
    CB a coûté arrondi(0,4 × 125) = 50. L'avoir de cette part rend −50.
    / A cascade part's credit note gives back the part's own cost (−50).
    """
    tarif_de_la_biere = creer_tarif_vendu(nom="Bière", prix_en_euros="5.00")
    vente = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        articles=[
            {
                "pricesold": tarif_de_la_biere,
                "quantite": Decimal("0.6"),
                "prix_unitaire": 500,
                "taux_tva": Decimal("0"),
                "total_catalogue_impose": 300,
                "prix_achat": 125,
                "payment_method": PaymentMethod.LOCAL_GIFT,
                "status": LigneArticle.VALID,
            },
            {
                "pricesold": tarif_de_la_biere,
                "quantite": Decimal("0.4"),
                "prix_unitaire": 500,
                "taux_tva": Decimal("20"),
                "total_catalogue_impose": 200,
                "prix_achat": 125,
                "payment_method": PaymentMethod.CC,
                "status": LigneArticle.VALID,
            },
        ],
        reglements=[
            {"moyen": PaymentMethod.LOCAL_GIFT, "montant": 300},
            {"moyen": PaymentMethod.CC, "montant": 200},
        ],
    )
    part_en_carte = vente.articles.get(payment_method=PaymentMethod.CC)
    assert part_en_carte.cout_achat == 50

    avoir = avoir_de_la_ligne_par_le_service(part_en_carte, part_en_carte.qty)

    assert avoir.cout_achat == -50


def test_cout_de_l_avoir_d_un_retour_de_consigne_est_positif(lieu):
    """
    Un retour de consigne (vente AVOIR de caisse, prix −100, coût −30 : le gobelet rendu
    retire son coût). L'avoir de ce retour remet le coût : +30.
    / A deposit return has a cost of −30: its credit note puts it back (+30).
    """
    tarif_du_retour = creer_tarif_vendu(nom="Retour gobelet", prix_en_euros="-1.00")
    vente_du_retour = fabriquer_vente_encaissee(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.AVOIR,
        articles=[
            {
                "pricesold": tarif_du_retour,
                "quantite": Decimal("1"),
                "prix_unitaire": -100,
                "taux_tva": Decimal("20"),
                "prix_achat": -30,
                "payment_method": PaymentMethod.CASH,
                "status": LigneArticle.VALID,
            }
        ],
        reglements=[{"moyen": PaymentMethod.CASH, "montant": -100}],
    )
    ligne_du_retour = vente_du_retour.articles.get()
    assert ligne_du_retour.cout_achat == -30

    avoir = avoir_de_la_ligne_par_le_service(ligne_du_retour, Decimal("1"))

    assert avoir.cout_achat == 30


def test_cout_de_l_avoir_ligne_sans_cout_reste_sans_cout(lieu):
    """
    Une ligne sans coût d'achat (prix d'achat inconnu, `cout_achat` vide) : l'avoir n'a
    pas de coût non plus (vide, jamais 0 : un coût inconnu n'est pas un coût nul).
    / A line without cost: the credit note has no cost either (empty, never 0).
    """
    ligne_sans_cout = ligne_d_une_vente_en_especes(
        {
            "pricesold": creer_tarif_vendu(nom="Planche", prix_en_euros="4.00"),
            "quantite": Decimal("1"),
            "prix_unitaire": 400,
            "taux_tva": Decimal("10"),
        }
    )
    assert ligne_sans_cout.cout_achat is None

    avoir = avoir_de_la_ligne_par_le_service(ligne_sans_cout, Decimal("1"))

    assert avoir.cout_achat is None


def test_cout_impose_qui_n_est_pas_un_entier_refuse(lieu):
    """
    Un coût d'achat imposé à `ajouter_article` est déjà en centimes entiers : un
    `Decimal` (montant recalculé ailleurs) est refusé, au lieu d'être arrondi en
    silence. Aucun article n'est écrit.
    / An imposed purchase cost must be whole cents (int): a Decimal is refused.
    """
    vente_d_avoir = services_vente.ouvrir_vente(
        origine=SaleOrigin.ADMIN, nature=Vente.Nature.AVOIR
    )

    with pytest.raises(ValueError, match="coût d'achat imposé"):
        services_vente.ajouter_article(
            vente_d_avoir,
            pricesold=creer_tarif_vendu(nom="Jus", prix_en_euros="3.50"),
            quantite=Decimal("-1"),
            prix_unitaire=350,
            taux_tva=Decimal("20"),
            cout_achat_impose=Decimal("-120"),
        )

    assert not LigneArticle.objects.filter(vente=vente_d_avoir).exists()
