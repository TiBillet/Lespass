"""
Tests de caractérisation : les ANNULATIONS et les AVOIRS (parcours P5, P6, P7, P8).
/ Characterization tests: CANCELLATIONS and CREDIT NOTES (flows P5, P6, P7, P8).

LOCALISATION : tests/pytest/test_caracterisation_annulations.py

À QUOI SERVENT CES TESTS
Un test de caractérisation FIGE le comportement d'aujourd'hui. Il ne dit pas si ce
comportement est bon : il dit « voilà ce que fait le code ». Il est vert sur le code
actuel. S'il tombe pendant le chantier 05 « montants entiers », c'est qu'une logique
métier a changé sans le vouloir : on s'arrête et on pose la question au mainteneur.
Seuls les tests listés dans la fiche A′ §4 ont le droit de changer, dans la fiche qui
change volontairement le comportement (leur docstring le dit).
/ A characterization test FREEZES today's behaviour. It is green on the current code.
Only the tests listed in sheet A′ §4 may change, in the sheet that changes the behaviour.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-A2-caracterisation.md
Détail des parcours : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-machine-a-etats.md (§4, §6).

CE QUE CES TESTS REGARDENT (et rien d'autre)
- les statuts finaux, relus en base : paiement, lignes de vente, réservation, billets,
  adhésion ;
- les appels au remboursement Stripe (`stripe.Refund.create`), simulé : leur nombre et
  le montant demandé ;
- les tâches Celery demandées : leur nom et leurs arguments ;
- la charge utile envoyée à l'ancien LaBoutik pour chaque avoir ou remboursement
  (`LigneArticleSerializer`, tâche `send_refund_to_laboutik`).
Ils ne lisent JAMAIS directement sur la ligne un champ que le chantier retire
(`payment_method`, `asset`, `wallet`…) : c'est la charge utile qui fait contrat.
/ They only read final statuses, Stripe refund calls, requested Celery tasks and the
legacy LaBoutik payload.

CODE PARCOURU / CODE EXERCISED
- BaseBillet/views.py — MyAccount.cancel_ticket, MyAccount.cancel_reservation (le client),
  MembershipMVT.cancel (l'admin annule une adhésion) ;
- BaseBillet/models.py — Reservation.cancel_and_refund_ticket, cancel_and_refund_resa,
  _lignes_hors_stripe, _creer_avoir, total_paid ;
- PaiementStripe/utils.py — partial_refund_payment (remboursement Stripe) ;
- Administration/admin_tenant.py — emettre_avoir (bouton « Avoir » d'une ligne de vente),
  TicketAdmin.action_cancel_refund_selected (« Cancel and refund » des billets) ;
- laboutik/views.py — PaiementViewSet.payer (un billet vendu à la caisse et offert par
  le gérant).

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin, rien ne reste
en base de dev. Stripe (session, catalogue, remboursement) et Celery sont simulés : aucun
appel réseau, aucune tâche envoyée au worker. Les tâches lancées en `transaction.on_commit`
sont exécutées par `django_capture_on_commit_callbacks(execute=True)` (tests/PIEGES.md 13.14).
La caisse est activée en mémoire, le temps d'une vente, par `configuration_modifiee()`.
/ Rolled-back transaction per test. Stripe (including refunds) and Celery are faked.
The register module is switched on in memory, for one sale only.

L'assistant `etat_metier()` et les gestes d'achat en ligne viennent du premier fichier
de caractérisation, `test_caracterisation_en_ligne.py`.
/ `etat_metier()` and the online buying helpers come from the first characterization file.

Lancer / Run : make test ARGS="tests/pytest/test_caracterisation_annulations.py"
"""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

from ApiBillet.serializers import LigneArticleSerializer, get_or_create_price_sold
from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import (
    LigneArticle,
    Membership,
    Paiement_stripe,
    PaymentMethod,
    Reservation,
    SaleOrigin,
    Ticket,
)
from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    configuration_modifiee,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fabriques_reservation import vente_admin_especes
from laboutik.models import CartePrimaire, PointDeVente
from QrcodeCashless.models import CarteCashless
from test_caracterisation_en_ligne import (
    EN_TETE_HTMX,
    adherer_sans_panier,
    arguments_des_taches,
    creer_un_administrateur_du_lieu,
    etat_metier,
    reserver_des_billets_sans_panier,
    revenir_de_stripe_adhesion,
    revenir_de_stripe_billetterie,
)

pytestmark = pytest.mark.django_db


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

    `remboursement_stripe` remplace `stripe.Refund.create` : on lit ses appels.
    `taches_demandees` se remplit au fil du test : une paire (nom court, arguments) par
    tâche demandée.
    / `remboursement_stripe` replaces `stripe.Refund.create`: its calls are read.
    """
    remboursement_reussi = MagicMock(status="succeeded")
    with tenant_context(tenant):
        with catalogue_stripe_simule() as catalogue_stripe:
            with taches_celery_enregistrees() as taches_demandees:
                with patch(
                    "stripe.Refund.create", return_value=remboursement_reussi
                ) as remboursement_stripe:
                    yield SimpleNamespace(
                        tenant=tenant,
                        stripe=mock_stripe,
                        catalogue_stripe=catalogue_stripe,
                        taches_demandees=taches_demandees,
                        remboursement_stripe=remboursement_stripe,
                    )


# --------------------------------------------------------------------------
# Assistants de lecture
# / Reading helpers
# --------------------------------------------------------------------------


def moyen_puis_montant_de_la_charge_utile(charge_utile):
    """Clé de tri des charges utiles : le moyen de paiement, puis le montant.
    / Sort key for payloads: payment method, then amount."""
    return (charge_utile["payment_method"], charge_utile["amount"])


def charges_utiles_des_avoirs_envoyees_a_laboutik(taches_demandees):
    """
    Ce que chaque tâche `send_refund_to_laboutik` demandée enverrait à l'ancien LaBoutik.
    / What each requested `send_refund_to_laboutik` task would send to legacy LaBoutik.

    Cette tâche part pour chaque ligne négative : remboursement Stripe (`R`) ou avoir
    (`N`). Elle est interceptée : elle ne tourne pas. On refait ici la même sérialisation
    qu'elle (`LigneArticleSerializer`, BaseBillet/tasks.py `send_refund_to_laboutik`), sur
    la ligne qu'elle a reçue en argument. On garde quatre champs du contrat : le moyen de
    paiement, le montant (prix unitaire, en centimes), la quantité (négative), le statut.
    La liste est triée par moyen, puis par montant.
    / One payload per negative line (refund or credit note). We replay the task's
    serialization, keep four contract fields, and sort by method then amount.
    """
    charges_utiles = []
    for arguments in arguments_des_taches(taches_demandees, "send_refund_to_laboutik"):
        pk_de_la_ligne = arguments[0]
        ligne = LigneArticle.objects.get(pk=pk_de_la_ligne)
        charge_complete = LigneArticleSerializer(ligne).data
        charges_utiles.append(
            {
                "payment_method": charge_complete["payment_method"],
                "amount": charge_complete["amount"],
                "qty": charge_complete["qty"],
                "status": charge_complete["status"],
            }
        )
    charges_utiles.sort(key=moyen_puis_montant_de_la_charge_utile)
    return charges_utiles


def statuts_des_lignes_de_la_reservation(reservation):
    """
    Les statuts des lignes de vente rattachées à la réservation, triés.
    Sert aux ventes sans paiement Stripe (admin, caisse), que `etat_metier` ne lit pas.
    / Sorted statuses of the sale lines linked to the reservation (non-Stripe sales).
    """
    statuts_des_lignes = []
    for ligne in LigneArticle.objects.filter(reservation=reservation):
        statuts_des_lignes.append(ligne.status)
    return sorted(statuts_des_lignes)


def statuts_des_lignes_de_l_adhesion(adhesion):
    """Les statuts des lignes de vente rattachées à l'adhésion, triés.
    / Sorted statuses of the sale lines linked to the membership."""
    statuts_des_lignes = []
    for ligne in LigneArticle.objects.filter(membership=adhesion):
        statuts_des_lignes.append(ligne.status)
    return sorted(statuts_des_lignes)


# --------------------------------------------------------------------------
# Gestes du client, de l'admin et de la caisse
# / Customer, admin and cash register actions
# --------------------------------------------------------------------------


def acheter_des_billets_payes_par_stripe(acheteur, billetterie, quantite):
    """
    Le client réserve `quantite` billets sans panier, puis revient de Stripe : payé.
    Rend la réservation et son paiement Stripe.
    / The buyer books tickets without cart, then comes back from Stripe: paid.
    """
    client_de_l_acheteur = client_connecte(acheteur)
    reserver_des_billets_sans_panier(
        client_de_l_acheteur,
        acheteur,
        billetterie.evenement,
        {billetterie.tarif: quantite},
    )
    reservation = Reservation.objects.get(
        user_commande=acheteur, event=billetterie.evenement
    )
    paiement = reservation.paiements.get()
    revenir_de_stripe_billetterie(client_de_l_acheteur, paiement)
    return SimpleNamespace(reservation=reservation, paiement=paiement)


def acheter_une_adhesion_payee_par_stripe(acheteur, adhesion):
    """
    Le client prend l'adhésion sans panier, puis revient de Stripe : payée.
    Rend l'adhésion et son paiement Stripe.
    / The buyer takes the membership without cart, then comes back from Stripe: paid.
    """
    client_de_l_acheteur = client_connecte(acheteur)
    adherer_sans_panier(client_de_l_acheteur, acheteur, adhesion.tarif)
    adhesion_creee = Membership.objects.get(user=acheteur, price=adhesion.tarif)
    paiement = adhesion_creee.stripe_paiement.get()
    revenir_de_stripe_adhesion(client_de_l_acheteur, paiement)
    return SimpleNamespace(adhesion=adhesion_creee, paiement=paiement)


def client_de_mon_compte(lieu, utilisateur):
    """
    Le client connecté à « Mon compte », avec un compte actif et un portefeuille local.
    / The buyer logged in to "My account", with an active account and a local wallet.

    « Mon compte » refuse un compte inactif (session ignorée) et demande un portefeuille à
    Fedow en HTTP si le compte n'en a pas (BaseBillet/views.py, `MyAccount.dispatch`). Un
    client qui se connecte a validé son e-mail : son compte est actif. On pose donc
    l'ÉTAT DE DÉPART par `update()`, qui ne déclenche aucun signal (tests/PIEGES.md 12.17).
    / "My account" ignores inactive accounts and asks Fedow for a wallet over HTTP: the
    starting state is set with update(), which fires no signal.
    """
    portefeuille_local = Wallet.objects.create(
        name=f"TEST_annulations portefeuille {identifiant_unique()}",
        origin=lieu.tenant,
    )
    TibilletUser.objects.filter(pk=utilisateur.pk).update(
        is_active=True, wallet=portefeuille_local
    )
    utilisateur.refresh_from_db()
    return client_connecte(utilisateur)


def annuler_un_billet_depuis_mon_compte(client_de_l_acheteur, billet):
    """Le client annule un billet depuis « Mon compte » (bouton du billet).
    / The buyer cancels one ticket from "My account"."""
    return client_de_l_acheteur.post(
        f"/my_account/{billet.pk}/cancel_ticket/", **EN_TETE_HTMX
    )


def annuler_une_reservation_depuis_mon_compte(client_de_l_acheteur, reservation):
    """Le client annule toute sa réservation depuis « Mon compte ».
    / The buyer cancels the whole reservation from "My account"."""
    return client_de_l_acheteur.post(
        f"/my_account/{reservation.pk}/cancel_reservation/", **EN_TETE_HTMX
    )


def annuler_des_billets_depuis_l_admin(client_de_l_admin, billets):
    """
    L'admin coche des billets dans la liste des billets et lance l'action
    « Cancel and refund ». Si tous les billets d'une réservation sont cochés, c'est
    toute la réservation qui est annulée (`cancel_and_refund_resa`).
    / The admin ticks tickets in the ticket list and runs "Cancel and refund".
    """
    billets_coches = []
    for billet in billets:
        billets_coches.append(str(billet.pk))
    return client_de_l_admin.post(
        "/admin/BaseBillet/ticket/",
        {
            "action": "action_cancel_refund_selected",
            "_selected_action": billets_coches,
        },
    )


def emettre_un_avoir_depuis_l_admin(client_de_l_admin, ligne, moyen_rembourse=None):
    """
    L'admin clique « Avoir » sur une ligne de vente (liste des ventes) : l'écran
    « Émettre un avoir » s'ouvre (GET), puis l'admin le valide (POST). Le moyen
    « Remboursé par » n'est envoyé que s'il est donné : une ligne payée par Stripe n'a
    pas ce champ. Rend la réponse de la validation.
    / The admin clicks "Credit note": the screen opens (GET), then is confirmed (POST),
    with the "Refunded by" method only if given. Returns the confirmation response.
    """
    url_de_l_avoir = f"/admin/BaseBillet/lignearticle/{ligne.pk}/emettre_avoir/"
    client_de_l_admin.get(url_de_l_avoir)
    donnees_du_formulaire = {}
    if moyen_rembourse is not None:
        donnees_du_formulaire["moyen_rembourse"] = moyen_rembourse
    return client_de_l_admin.post(url_de_l_avoir, donnees_du_formulaire)


def annuler_une_adhesion_avec_avoirs_depuis_l_admin(client_de_l_admin, adhesion):
    """
    L'admin annule l'adhésion depuis sa fiche, case « créer les avoirs » cochée.
    / The admin cancels the membership from its page, "create credit notes" ticked.
    """
    return client_de_l_admin.post(
        f"/memberships/{adhesion.pk}/cancel/",
        {"with_credit_note": "1"},
        **EN_TETE_HTMX,
    )


def vendre_un_billet_offert_a_la_caisse(lieu, acheteur, billetterie):
    """
    La caisse vend UN billet de l'événement et le gérant l'OFFRE (tuile OFFRIR, code de
    paiement « gift »). Rend la réservation créée.
    / The register sells ONE ticket and the manager OFFERS it (GIFT tile, "gift" code).

    Le geste passe par la vraie route de paiement de la caisse, `POST
    /laboutik/paiement/payer/` (laboutik/views.py, `PaiementViewSet.payer`). Le formulaire
    est celui de l'écran (#addition-form) : la clé `repid-<événement>__<tarif>` d'une tuile
    billet porte la quantité. Le client est identifié par son e-mail.
    / The real register payment route, with the screen's form. The buyer is identified
    by email.

    ÉTAT DE DÉPART, posé ici :
    - la caisse est activée EN MÉMOIRE, le temps de la vente seulement :
      `configuration_modifiee()` n'enregistre jamais la `Configuration` (tests/PIEGES.md
      13.22) ;
    - un point de vente « billetterie » : lui seul lit les clés de tuile billet. Il est
      caché, comme tout point de vente de test (tests/PIEGES.md 9.41) ;
    - le caissier est un administrateur du lieu connecté : la caisse accepte sa session
      (BaseBillet/permissions.py) ;
    - sa carte primaire est en MODE GÉRANT et ouvre ce point de vente. OFFRIR un panier
      payant l'exige : le serveur lit le mode gérant en base, à partir du tag envoyé dans
      `tag_id_cm` (laboutik/views.py, `_panier_peut_etre_offert`).
    La ligne offerte garde le prix du billet (`amount` = prix), moyen « offert ».
    / STARTING STATE: register switched on in memory, hidden ticketing point of sale,
    admin cashier, manager-mode primary card sent as `tag_id_cm`. The gifted line keeps
    the ticket price.
    """
    # ÉTAT DE DÉPART : le point de vente et la carte du gérant.
    # / STARTING STATE: the point of sale and the manager's card.
    point_de_vente_billetterie = PointDeVente.objects.create(
        name=f"TEST_annulations billetterie {identifiant_unique()}",
        comportement=PointDeVente.BILLETTERIE,
        hidden=True,
    )

    # `tag_id` et `number` font 8 caractères au plus (tests/PIEGES.md 9.31).
    # / tag_id and number are 8 characters max.
    identifiant_de_la_carte = identifiant_unique().upper()
    carte_du_gerant = CarteCashless.objects.create(
        tag_id=identifiant_de_la_carte,
        number=identifiant_de_la_carte,
        uuid=uuid.uuid4(),
    )
    carte_primaire_du_gerant = CartePrimaire.objects.create(
        carte=carte_du_gerant,
        edit_mode=True,
    )
    carte_primaire_du_gerant.points_de_vente.add(point_de_vente_billetterie)

    # Le formulaire de l'écran : un billet, offert, pour le client identifié par e-mail.
    # / The screen's form: one ticket, gifted, for the buyer identified by email.
    client_du_caissier = creer_un_administrateur_du_lieu(lieu)
    prix_du_billet_en_centimes = int(round(billetterie.tarif.prix * 100))
    cle_de_la_tuile_billet = (
        f"repid-{billetterie.evenement.uuid}__{billetterie.tarif.uuid}"
    )
    donnees_du_formulaire = {
        "uuid_pv": str(point_de_vente_billetterie.uuid),
        "tag_id_cm": carte_du_gerant.tag_id,
        "moyen_paiement": "gift",
        "total": str(prix_du_billet_en_centimes),
        "given_sum": "0",
        "email_adhesion": acheteur.email,
        cle_de_la_tuile_billet: "1",
    }
    # Le module caisse a besoin du module monnaie locale.
    # / The register module needs the local currency module.
    with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
        reponse_de_la_caisse = client_du_caissier.post(
            "/laboutik/paiement/payer/", donnees_du_formulaire
        )

    assert reponse_de_la_caisse.status_code == 200
    return Reservation.objects.get(user_commande=acheteur, event=billetterie.evenement)


def creer_une_adhesion_payee_trois_fois(acheteur, adhesion):
    """
    ÉTAT DE DÉPART : une adhésion en abonnement, payée trois fois par Stripe — l'achat
    (carte, `SN`) puis deux renouvellements (prélèvement récurrent, `SR`), 15 € chacun.
    Chaque paiement a son `Paiement_stripe` validé et sa ligne de vente validée.
    Fabriqué par `create(status=…)`, sans passer par la machine à états : il sert à poser
    des ventes antérieures, jamais à tester un paiement (tests/PIEGES.md 9.41, 12.17).
    / STARTING STATE: a subscription paid three times by Stripe (purchase + two renewals),
    built with create(status=...), never used to test a payment.
    """
    adhesion_abonnee = Membership.objects.create(
        user=acheteur,
        price=adhesion.tarif,
        status=Membership.AUTO,
        first_name="Ada",
        last_name="Lovelace",
        stripe_id_subscription=f"sub_test_{identifiant_unique()}",
        current_iteration=3,
        deadline=timezone.now() + timedelta(days=300),
    )
    tarif_vendu = get_or_create_price_sold(adhesion.tarif)

    moyens_des_trois_paiements = [
        PaymentMethod.STRIPE_NOFED,
        PaymentMethod.STRIPE_RECURENT,
        PaymentMethod.STRIPE_RECURENT,
    ]
    for moyen_de_paiement in moyens_des_trois_paiements:
        paiement_valide = Paiement_stripe.objects.create(
            user=acheteur,
            status=Paiement_stripe.VALID,
            payment_intent_id=f"pi_test_{identifiant_unique()}",
        )
        LigneArticle.objects.create(
            pricesold=tarif_vendu,
            qty=1,
            amount=1500,
            membership=adhesion_abonnee,
            paiement_stripe=paiement_valide,
            payment_method=moyen_de_paiement,
            sale_origin=SaleOrigin.LESPASS,
            status=LigneArticle.VALID,
        )
    return adhesion_abonnee


# --------------------------------------------------------------------------
# P5 — Le client annule un billet payé par Stripe
# / P5 — The buyer cancels a ticket paid through Stripe
# --------------------------------------------------------------------------


def test_annuler_un_billet_stripe_rembourse_un_billet(
    lieu, django_capture_on_commit_callbacks
):
    """
    P5 : trois billets à 10 € payés par Stripe ; le client annule UN billet depuis
    « Mon compte ».
    Stripe reçoit UNE demande de remboursement, du prix d'un seul billet (1000 centimes).
    Le paiement passe « remboursé en partie » (`H`). Une ligne négative « remboursée »
    (`R`, quantité −1) s'ajoute à la ligne validée. Le billet annulé passe `R`, les deux
    autres restent actifs (`K`) ; la réservation reste payée (`P`).
    Tâches : l'envoi du remboursement à l'ancien LaBoutik (moyen « Stripe CB »), puis le
    mail d'annulation du billet.
    / P5: 3 tickets paid by Stripe, the buyer cancels ONE. One Stripe refund of one ticket
    price; payment PARTIALLY_REFUNDED; one REFUNDED line, qty -1; LaBoutik refund + mail.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    achat = acheter_des_billets_payes_par_stripe(acheteur, concert, quantite=3)
    billet_a_annuler = achat.reservation.tickets.order_by("pk").first()
    # On ne garde que les tâches demandées par l'annulation.
    # / Keep only the tasks requested by the cancellation.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = annuler_un_billet_depuis_mon_compte(
            client_de_mon_compte(lieu, acheteur), billet_a_annuler
        )

    assert reponse.status_code == 200
    taches_de_l_annulation = lieu.taches_demandees
    etat_attendu = {
        "paiement": Paiement_stripe.PARTIALLY_REFUNDED,
        "lignes": [LigneArticle.REFUNDED, LigneArticle.VALID],
        "reservations": [Reservation.PAID],
        "billets": [Ticket.NOT_SCANNED, Ticket.NOT_SCANNED, Ticket.CANCELED],
        "taches": ["send_refund_to_laboutik", "send_ticket_cancellation_user"],
    }
    assert (
        etat_metier(
            paiement=achat.paiement,
            reservations=[achat.reservation],
            taches_demandees=taches_de_l_annulation,
        )
        == etat_attendu
    )

    # Un seul remboursement Stripe, du prix d'UN billet, sur le paiement de l'achat.
    # / One single Stripe refund, of ONE ticket price, on the purchase payment.
    assert lieu.remboursement_stripe.call_count == 1
    arguments_du_remboursement = lieu.remboursement_stripe.call_args.kwargs
    assert arguments_du_remboursement["amount"] == 1000
    assert arguments_du_remboursement["payment_intent"] == "pi_test_mock_intent"

    billet_a_annuler.refresh_from_db()
    assert billet_a_annuler.status == Ticket.CANCELED
    assert arguments_des_taches(
        taches_de_l_annulation, "send_ticket_cancellation_user"
    ) == [(str(billet_a_annuler.uuid),)]

    assert charges_utiles_des_avoirs_envoyees_a_laboutik(taches_de_l_annulation) == [
        {
            "payment_method": PaymentMethod.STRIPE_NOFED,
            "amount": 1000,
            "qty": "-1.000000",
            "status": LigneArticle.REFUNDED,
        },
    ]


# --------------------------------------------------------------------------
# P6 — Annulation d'une réservation payée hors Stripe
# / P6 — Cancelling a reservation paid outside Stripe
# --------------------------------------------------------------------------


def test_annulation_utilisateur_reservation_admin_especes_cree_un_avoir(
    lieu, django_capture_on_commit_callbacks
):
    """
    P6, par le client : deux billets à 10 € vendus dans l'admin, payés en espèces. Le
    client annule sa réservation depuis « Mon compte ».
    Aucun appel à Stripe. Un avoir (`N`, quantité −2) s'ajoute à la ligne validée ; la
    réservation et ses deux billets passent annulés. L'ancien LaBoutik reçoit l'avoir
    avec le moyen « espèces » (`CA`). Puis le mail d'annulation de la réservation.
    Change en D (décision D31) : sans écran « Remboursé par », le client n'obtient plus
    d'avoir hors Stripe ; seuls la réservation et les billets sont annulés.
    / P6 by the buyer: 2 admin cash tickets cancelled from "My account". No Stripe call;
    one CREDIT_NOTE line qty -2 sent to LaBoutik as cash. Changes in D (D31).
    """
    concert = creer_evenement_avec_tarif(prix="10.00")
    reservation, _ligne_de_la_vente = vente_admin_especes(
        lieu.tenant, concert.evenement.uuid, concert.tarif.uuid, qty=2
    )
    acheteur = reservation.user_commande
    # On ne garde que les tâches demandées par l'annulation.
    # / Keep only the tasks requested by the cancellation.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = annuler_une_reservation_depuis_mon_compte(
            client_de_mon_compte(lieu, acheteur), reservation
        )

    assert reponse.status_code == 200
    taches_de_l_annulation = lieu.taches_demandees
    etat_attendu = {
        "reservations": [Reservation.CANCELED],
        "billets": [Ticket.CANCELED, Ticket.CANCELED],
        "taches": ["send_refund_to_laboutik", "send_reservation_cancellation_user"],
    }
    assert (
        etat_metier(
            reservations=[reservation],
            taches_demandees=taches_de_l_annulation,
        )
        == etat_attendu
    )
    assert statuts_des_lignes_de_la_reservation(reservation) == [
        LigneArticle.CREDIT_NOTE,
        LigneArticle.VALID,
    ]
    assert lieu.remboursement_stripe.call_count == 0

    assert charges_utiles_des_avoirs_envoyees_a_laboutik(taches_de_l_annulation) == [
        {
            "payment_method": PaymentMethod.CASH,
            "amount": 1000,
            "qty": "-2.000000",
            "status": LigneArticle.CREDIT_NOTE,
        },
    ]


def test_annuler_un_billet_caisse_offert_cree_un_avoir(
    lieu, django_capture_on_commit_callbacks
):
    """
    P6, par l'admin : un billet à 15 € vendu à la caisse et OFFERT par le caissier. La
    ligne offerte garde le prix du billet (1500 centimes), moyen « offert » (`NA`).
    L'admin annule ce billet (action « Cancel and refund » de la liste des billets) :
    c'est le seul billet de la réservation, donc toute la réservation est annulée.
    Aucun appel à Stripe. Un avoir (`N`, quantité −1, 1500 centimes, moyen « offert »)
    s'ajoute à la ligne validée : la garde « payé mais rien de remboursable » voit un
    montant payé non nul (`total_paid()` lit `amount × qty`, offert compris).
    Réservation et billet annulés. Tâches : l'avoir envoyé à l'ancien LaBoutik, puis le
    mail d'annulation de la réservation.
    Change en G : `total_paid()` lira `total_ttc`, nul pour un billet entièrement offert ;
    plus d'avoir d'argent, seulement la trace de l'offert annulé.
    / P6 by the admin: a register ticket OFFERED at 15 € is cancelled: a CREDIT_NOTE line
    of the full price, method "offered", is created. Changes in G (total_paid on total_ttc).
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="15.00")
    reservation = vendre_un_billet_offert_a_la_caisse(lieu, acheteur, concert)
    billet_offert = reservation.tickets.get()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    # On ne garde que les tâches demandées par l'annulation.
    # / Keep only the tasks requested by the cancellation.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = annuler_des_billets_depuis_l_admin(client_de_l_admin, [billet_offert])

    assert reponse.status_code == 302
    taches_de_l_annulation = lieu.taches_demandees
    etat_attendu = {
        "reservations": [Reservation.CANCELED],
        "billets": [Ticket.CANCELED],
        "taches": ["send_refund_to_laboutik", "send_reservation_cancellation_user"],
    }
    assert (
        etat_metier(
            reservations=[reservation],
            taches_demandees=taches_de_l_annulation,
        )
        == etat_attendu
    )
    assert statuts_des_lignes_de_la_reservation(reservation) == [
        LigneArticle.CREDIT_NOTE,
        LigneArticle.VALID,
    ]
    assert lieu.remboursement_stripe.call_count == 0

    assert charges_utiles_des_avoirs_envoyees_a_laboutik(taches_de_l_annulation) == [
        {
            "payment_method": PaymentMethod.FREE,
            "amount": 1500,
            "qty": "-1.000000",
            "status": LigneArticle.CREDIT_NOTE,
        },
    ]


# --------------------------------------------------------------------------
# P7 — L'admin annule une adhésion
# / P7 — The admin cancels a membership
# --------------------------------------------------------------------------


def test_annulation_adhesion_avoirs_de_tous_les_renouvellements(
    lieu, django_capture_on_commit_callbacks
):
    """
    P7 : une adhésion en abonnement payée trois fois par Stripe (l'achat puis deux
    renouvellements, 15 € chacun). L'admin l'annule, case « créer les avoirs » cochée.
    L'adhésion passe « annulée par l'admin » (`AC`), son échéance reste posée. TROIS
    avoirs (`N`, quantité −1) sont créés : un par paiement, l'achat ET les deux
    renouvellements (voir T7). Aucun appel à Stripe.
    Tâches : un envoi à l'ancien LaBoutik par avoir (moyens « Stripe CB » puis deux fois
    « Stripe récurrent »), puis le webhook d'adhésion après la validation en base.
    Change en D (décision D30) : un seul avoir, pour le dernier paiement.
    / P7: a membership paid 3 times is cancelled with credit notes: ADMIN_CANCELED, THREE
    credit notes (purchase and both renewals), no Stripe call. Changes in D (D30).
    """
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00", recurrente=True)
    adhesion_abonnee = creer_une_adhesion_payee_trois_fois(acheteur, adhesion)
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    # On oublie les tâches demandées par la préparation (produit, adhésion).
    # / Forget the tasks requested while preparing (product, membership).
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = annuler_une_adhesion_avec_avoirs_depuis_l_admin(
            client_de_l_admin, adhesion_abonnee
        )

    assert reponse.status_code == 204
    taches_de_l_annulation = lieu.taches_demandees
    etat_attendu = {
        "adhesion": Membership.ADMIN_CANCELED,
        "adhesion_a_une_echeance": True,
        "taches": [
            "send_refund_to_laboutik",
            "send_refund_to_laboutik",
            "send_refund_to_laboutik",
            "webhook_membership",
        ],
    }
    assert (
        etat_metier(
            adhesion=adhesion_abonnee,
            taches_demandees=taches_de_l_annulation,
        )
        == etat_attendu
    )
    assert statuts_des_lignes_de_l_adhesion(adhesion_abonnee) == [
        LigneArticle.CREDIT_NOTE,
        LigneArticle.CREDIT_NOTE,
        LigneArticle.CREDIT_NOTE,
        LigneArticle.VALID,
        LigneArticle.VALID,
        LigneArticle.VALID,
    ]
    assert lieu.remboursement_stripe.call_count == 0

    # Charges utiles triées par moyen : « Stripe CB » (SN) avant « Stripe récurrent » (SR).
    # / Payloads sorted by method: SN before SR.
    assert charges_utiles_des_avoirs_envoyees_a_laboutik(taches_de_l_annulation) == [
        {
            "payment_method": PaymentMethod.STRIPE_NOFED,
            "amount": 1500,
            "qty": "-1.000000",
            "status": LigneArticle.CREDIT_NOTE,
        },
        {
            "payment_method": PaymentMethod.STRIPE_RECURENT,
            "amount": 1500,
            "qty": "-1.000000",
            "status": LigneArticle.CREDIT_NOTE,
        },
        {
            "payment_method": PaymentMethod.STRIPE_RECURENT,
            "amount": 1500,
            "qty": "-1.000000",
            "status": LigneArticle.CREDIT_NOTE,
        },
    ]


# --------------------------------------------------------------------------
# P7 / P8 — Les avoirs de l'admin n'appellent jamais Stripe (D27)
# / P7 / P8 — Admin credit notes never call Stripe (D27)
# --------------------------------------------------------------------------


def test_avoirs_admin_et_annulation_adhesion_n_appellent_pas_stripe(
    lieu, django_capture_on_commit_callbacks
):
    """
    P7 et P8 (T8, décision D27) : un billet à 10 € et une adhésion à 15 €, payés par
    Stripe. L'admin émet un avoir sur la ligne du billet (bouton « Avoir »), puis annule
    l'adhésion avec avoirs.
    Stripe n'est JAMAIS appelé pour rembourser : l'avoir est seulement comptable. Chaque
    ligne payée reçoit un avoir (`N`) ; les deux paiements Stripe restent validés (`V`) ;
    la réservation reste payée, son billet actif ; l'adhésion passe `AC`.
    Tâches : un envoi à l'ancien LaBoutik par avoir, moyen « Stripe CB » ; puis le webhook
    d'adhésion. Reste vert pendant tout le chantier.
    / P7/P8 (D27): admin credit note on a Stripe ticket line and membership cancellation
    with credit notes never call Stripe refund. Stays green through the whole chantier.
    """
    acheteur = creer_utilisateur()
    concert = creer_evenement_avec_tarif(prix="10.00")
    adhesion = creer_adhesion(prix="15.00")
    achat_du_billet = acheter_des_billets_payes_par_stripe(
        acheteur, concert, quantite=1
    )
    achat_de_l_adhesion = acheter_une_adhesion_payee_par_stripe(acheteur, adhesion)
    ligne_du_billet = LigneArticle.objects.get(paiement_stripe=achat_du_billet.paiement)
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    # On ne garde que les tâches demandées par les gestes de l'admin.
    # / Keep only the tasks requested by the admin's actions.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse_de_l_avoir = emettre_un_avoir_depuis_l_admin(
            client_de_l_admin, ligne_du_billet
        )
        reponse_de_l_annulation = annuler_une_adhesion_avec_avoirs_depuis_l_admin(
            client_de_l_admin, achat_de_l_adhesion.adhesion
        )

    assert reponse_de_l_avoir.status_code == 302
    assert reponse_de_l_annulation.status_code == 204

    # Le cœur du test : aucun remboursement Stripe demandé.
    # / The heart of the test: no Stripe refund requested.
    assert lieu.remboursement_stripe.call_count == 0

    taches_de_l_admin = lieu.taches_demandees
    etat_attendu_du_billet = {
        "paiement": Paiement_stripe.VALID,
        "lignes": [LigneArticle.CREDIT_NOTE, LigneArticle.VALID],
        "reservations": [Reservation.PAID],
        "billets": [Ticket.NOT_SCANNED],
    }
    assert (
        etat_metier(
            paiement=achat_du_billet.paiement,
            reservations=[achat_du_billet.reservation],
        )
        == etat_attendu_du_billet
    )
    etat_attendu_de_l_adhesion = {
        "paiement": Paiement_stripe.VALID,
        "lignes": [LigneArticle.CREDIT_NOTE, LigneArticle.VALID],
        "adhesion": Membership.ADMIN_CANCELED,
        "adhesion_a_une_echeance": True,
        "taches": [
            "send_refund_to_laboutik",
            "send_refund_to_laboutik",
            "webhook_membership",
        ],
    }
    assert (
        etat_metier(
            paiement=achat_de_l_adhesion.paiement,
            adhesion=achat_de_l_adhesion.adhesion,
            taches_demandees=taches_de_l_admin,
        )
        == etat_attendu_de_l_adhesion
    )

    # Avoir du billet (10 €) et avoir de l'adhésion (15 €), triés par montant.
    # / Ticket credit note (10 €) and membership credit note (15 €), sorted by amount.
    assert charges_utiles_des_avoirs_envoyees_a_laboutik(taches_de_l_admin) == [
        {
            "payment_method": PaymentMethod.STRIPE_NOFED,
            "amount": 1000,
            "qty": "-1.000000",
            "status": LigneArticle.CREDIT_NOTE,
        },
        {
            "payment_method": PaymentMethod.STRIPE_NOFED,
            "amount": 1500,
            "qty": "-1.000000",
            "status": LigneArticle.CREDIT_NOTE,
        },
    ]
