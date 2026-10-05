"""
Tests de caractérisation : les ventes EN LIGNE payées par Stripe (parcours P1, P2, P3, P15).
/ Characterization tests: ONLINE sales paid through Stripe (flows P1, P2, P3, P15).

LOCALISATION : tests/pytest/test_caracterisation_en_ligne.py

À QUOI SERVENT CES TESTS
Un test de caractérisation FIGE le comportement d'aujourd'hui. Il ne dit pas si ce
comportement est bon : il dit « voilà ce que fait le code ». Il est vert sur le code
actuel. S'il tombe pendant le chantier 05 « montants entiers », c'est qu'une logique
métier a changé sans le vouloir : on s'arrête et on pose la question au mainteneur.
/ A characterization test FREEZES today's behaviour. It is green on the current code.
If it fails during chantier 05, a business rule changed by accident: stop and ask.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-A2-caracterisation.md
Détail des parcours : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-machine-a-etats.md (§4, §6).

CE QUE CES TESTS REGARDENT (et rien d'autre)
- les statuts finaux, relus en base : paiement, lignes de vente, réservations, billets,
  adhésion, booking, commande ;
- les tâches Celery demandées : leur nom et leurs arguments ;
- la charge utile envoyée à l'ancien LaBoutik (`LigneArticleSerializer`).
Ils ne lisent JAMAIS directement sur la ligne un champ que le chantier retire
(`payment_method`, `asset`, `wallet`…) : c'est la charge utile qui fait contrat.
/ They only read final statuses, requested Celery tasks and the legacy LaBoutik payload.

CODE PARCOURU / CODE EXERCISED
- BaseBillet/models.py — Paiement_stripe.update_checkout_status() ;
- BaseBillet/signals.py — machine à états (PRE_SAVE_TRANSITIONS, set_ligne_article_paid) ;
- BaseBillet/triggers.py — trigger_A (adhésion), trigger_B (billet), trigger_C (ressource) ;
- ApiBillet/views.py — Webhook_stripe (SEPA en attente, SEPA refusé, renouvellement) ;
- Administration/admin_tenant.py — emettre_avoir (avoir émis dans l'admin).

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin, rien ne reste
en base de dev. Stripe (session, catalogue, facture) et Celery sont simulés : aucun appel
réseau, aucune tâche envoyée au worker. Les tâches lancées en `transaction.on_commit`
sont exécutées par `django_capture_on_commit_callbacks(execute=True)` (tests/PIEGES.md 13.14).
/ Rolled-back transaction per test. Stripe and Celery are faked. on_commit tasks are run
by `django_capture_on_commit_callbacks(execute=True)`.

L'assistant `etat_metier()` est commun à tous les fichiers de caractérisation
(`test_caracterisation_*.py`) : les autres fichiers l'importent d'ici.
/ `etat_metier()` is shared by all characterization files: they import it from here.

Lancer / Run : make test ARGS="tests/pytest/test_caracterisation_en_ligne.py"
"""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

from ApiBillet.serializers import LigneArticleSerializer
from BaseBillet.models import (
    Commande,
    LigneArticle,
    Membership,
    Paiement_stripe,
    PaymentMethod,
    Product,
    Reservation,
    Ticket,
)
from BaseBillet.services_commande import CommandeService
from BaseBillet.services_panier import PanierSession
from booking.models import Booking
from fabriques_panier import (
    ajouter_un_tarif,
    catalogue_stripe_simule,
    client_connecte,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_ressource_avec_tarif,
    creer_utilisateur,
    identifiant_unique,
    noms_des_taches,
    requete_avec_session,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db

# Les formulaires du front sont envoyés par HTMX (hx-post) : on envoie le même en-tête que
# le navigateur. Sans lui, certaines vues prennent une branche que le front n'utilise
# jamais (tests/PIEGES.md 13.8).
# / Front forms are sent by HTMX: send the same header as the browser.
EN_TETE_HTMX = {"HTTP_HX_REQUEST": "true"}

# Adresse du webhook Stripe (ApiBillet/urls.py, monté sous /api/).
# / Stripe webhook address.
URL_DU_WEBHOOK_STRIPE = "/api/webhook_stripe/"


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
    Le lieu `lespass`, avec Stripe (session + catalogue) et Celery simulés pendant tout le test.
    / The `lespass` venue, with Stripe (session + catalogue) and Celery faked for the whole test.

    `taches_demandees` se remplit au fil du test : une paire (nom court, arguments) par
    tâche demandée.
    / `taches_demandees` fills up during the test: one (short name, args) pair per task.
    """
    with tenant_context(tenant):
        with catalogue_stripe_simule() as catalogue_stripe:
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    stripe=mock_stripe,
                    catalogue_stripe=catalogue_stripe,
                    taches_demandees=taches_demandees,
                )


# --------------------------------------------------------------------------
# L'assistant commun : l'état métier relu en base
# / The shared helper: the business state read back from the database
# --------------------------------------------------------------------------


def etat_metier(
    paiement=None,
    reservations=None,
    adhesion=None,
    booking=None,
    commande=None,
    taches_demandees=None,
):
    """
    Relit en base les statuts utiles et les rend dans un dictionnaire simple.
    / Reads the useful statuses back from the database and returns them in a plain dict.

    LOCALISATION : tests/pytest/test_caracterisation_en_ligne.py
    Importé par les autres fichiers de caractérisation (test_caracterisation_*.py).

    Chaque test compare ce dictionnaire à un dictionnaire attendu, écrit en clair.
    On ne passe que les objets qui comptent pour le test : seules leurs clés
    apparaissent dans le résultat.
    / Each test compares this dict to an expected dict written out in full. Only the
    objects passed in appear in the result.

    Les clés possibles :
    - "paiement" : le statut du paiement Stripe ;
    - "lignes" : les statuts des lignes de vente de ce paiement, triés ;
    - "reservations" : le statut de chaque réservation, dans l'ordre donné ;
    - "billets" : les statuts de tous les billets de ces réservations, triés ;
    - "adhesion" et "adhesion_a_une_echeance" : le statut, et si `deadline` est posée ;
    - "booking" : le statut de la réservation de ressource ;
    - "commande" : le statut de la commande du panier ;
    - "taches" : les noms des tâches Celery demandées, dans l'ordre.
    / Possible keys: payment, sale lines (sorted), reservations, tickets (sorted),
    membership and whether its deadline is set, booking, order, task names.

    Les listes de lignes et de billets sont triées : leur ordre en base n'est pas garanti.
    / Line and ticket lists are sorted: their database order is not guaranteed.
    """
    etat = {}

    if paiement is not None:
        paiement.refresh_from_db()
        etat["paiement"] = paiement.status

        statuts_des_lignes = []
        for ligne in LigneArticle.objects.filter(paiement_stripe=paiement):
            statuts_des_lignes.append(ligne.status)
        etat["lignes"] = sorted(statuts_des_lignes)

    if reservations is not None:
        statuts_des_reservations = []
        statuts_des_billets = []
        for reservation in reservations:
            reservation.refresh_from_db()
            statuts_des_reservations.append(reservation.status)
            for billet in reservation.tickets.all():
                statuts_des_billets.append(billet.status)
        etat["reservations"] = statuts_des_reservations
        etat["billets"] = sorted(statuts_des_billets)

    if adhesion is not None:
        adhesion.refresh_from_db()
        etat["adhesion"] = adhesion.status
        etat["adhesion_a_une_echeance"] = adhesion.deadline is not None

    if booking is not None:
        booking.refresh_from_db()
        etat["booking"] = booking.status

    if commande is not None:
        commande.refresh_from_db()
        etat["commande"] = commande.status

    if taches_demandees is not None:
        etat["taches"] = noms_des_taches(taches_demandees)

    return etat


def arguments_des_taches(taches_demandees, nom_de_la_tache):
    """
    Les arguments de chaque demande d'une tâche, dans l'ordre des demandes.
    / The arguments of each request of one task, in request order.

    Exemple : `[(uuid_de_la_reservation,)]` pour un seul `webhook_reservation`.
    """
    arguments_trouves = []
    for nom, arguments in taches_demandees:
        if nom == nom_de_la_tache:
            arguments_trouves.append(arguments)
    return arguments_trouves


def montant_de_la_charge_utile(charge_utile):
    """Clé de tri des charges utiles : leur montant.
    / Sort key for payloads: their amount."""
    return charge_utile["amount"]


def charges_utiles_envoyees_a_laboutik(taches_demandees):
    """
    Ce que chaque tâche `send_sale_to_laboutik` demandée enverrait à l'ancien LaBoutik.
    / What each requested `send_sale_to_laboutik` task would send to legacy LaBoutik.

    La tâche est interceptée : elle ne tourne pas. On refait ici la même sérialisation
    qu'elle (`LigneArticleSerializer`, BaseBillet/tasks.py `send_sale_to_laboutik`), sur
    la ligne qu'elle a reçue en argument. On garde quatre champs du contrat : le moyen de
    paiement, le montant, la quantité, le statut. La liste est triée par montant.
    / The task is intercepted. We replay its serialization on the line it received, keep
    four contract fields, and sort by amount.
    """
    charges_utiles = []
    for arguments in arguments_des_taches(taches_demandees, "send_sale_to_laboutik"):
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
    charges_utiles.sort(key=montant_de_la_charge_utile)
    return charges_utiles


# --------------------------------------------------------------------------
# Gestes de l'acheteur, de l'admin et de Stripe
# / Buyer, admin and Stripe actions
# --------------------------------------------------------------------------


def reserver_des_billets_sans_panier(client, acheteur, evenement, quantites_par_tarif):
    """
    Réserve des billets par le formulaire de l'événement, sans panier (« Payer maintenant »).
    Crée la réservation, ses lignes de vente et le paiement Stripe (session simulée).
    / Books tickets through the event form, without cart. Creates the Stripe payment.

    `quantites_par_tarif` : {tarif: quantité}.
    """
    donnees_du_formulaire = {"event": str(evenement.uuid), "email": acheteur.email}
    for tarif, quantite in quantites_par_tarif.items():
        donnees_du_formulaire[str(tarif.uuid)] = str(quantite)
    return client.post(
        f"/event/{evenement.slug}/reservation/", donnees_du_formulaire, **EN_TETE_HTMX
    )


def adherer_sans_panier(client, acheteur, tarif):
    """
    Prend une adhésion par le formulaire d'adhésion, sans panier. Crée l'adhésion, sa ligne
    de vente et le paiement Stripe (session simulée).
    / Takes a membership through the membership form, without cart.
    """
    donnees_du_formulaire = {
        "price": str(tarif.uuid),
        "firstname": "Ada",
        "lastname": "Lovelace",
        "email": acheteur.email,
        "acknowledge": "true",
        "newsletter": "false",
    }
    return client.post("/memberships/", donnees_du_formulaire, **EN_TETE_HTMX)


def revenir_de_stripe_billetterie(client, paiement):
    """
    Joue le retour navigateur depuis Stripe (billets et panier). La vue relit la session
    Stripe simulée par `mock_stripe` : « payée » par défaut.
    Rejouer ce retour (touche F5) rejoue `update_checkout_status()`.
    / Plays the browser return from Stripe (tickets and cart). Replaying it = F5.
    """
    return client.get(f"/event/{paiement.uuid}/stripe_return/")


def revenir_de_stripe_adhesion(client, paiement):
    """Joue le retour navigateur depuis Stripe pour une adhésion prise sans panier.
    / Plays the browser return from Stripe for a membership taken without cart."""
    return client.get(f"/memberships/{paiement.uuid}/stripe_return/")


def envoyer_un_evenement_stripe(type_d_evenement, objet_de_l_evenement):
    """
    Envoie un événement au webhook Stripe du lieu, comme le fait Stripe.
    Le webhook ne vérifie pas de signature : il relit la session chez Stripe (simulé).
    / Posts an event to the venue's Stripe webhook, as Stripe does.
    """
    evenement_stripe = {
        "id": f"evt_test_{identifiant_unique()}",
        "type": type_d_evenement,
        "data": {"object": objet_de_l_evenement},
    }
    client_anonyme = client_connecte()
    return client_anonyme.post(
        URL_DU_WEBHOOK_STRIPE, evenement_stripe, content_type="application/json"
    )


def objet_session_de_paiement(lieu, identifiant_de_session):
    """
    La partie `data.object` d'un événement `checkout.session.*`, avec les seuls champs
    que lit le webhook : l'identifiant de session, l'adresse de retour, le lieu.
    / The `data.object` part of a `checkout.session.*` event, with only the fields read.
    """
    return {
        "id": identifiant_de_session,
        "success_url": "https://lespass.tibillet.localhost/memberships/stripe_return/",
        "metadata": {"tenant": str(lieu.tenant.uuid)},
    }


def creer_un_administrateur_du_lieu(lieu):
    """Un utilisateur administrateur du lieu, connecté à l'admin.
    / A venue admin user, logged in to the admin."""
    administrateur = creer_utilisateur(prenom="Admin", nom="Lieu")
    administrateur.client_admin.add(lieu.tenant)
    return client_connecte(administrateur)


# --------------------------------------------------------------------------
# P1 — Billets en ligne, sans panier, Stripe accepté
# / P1 — Online tickets, without cart, Stripe accepted
# --------------------------------------------------------------------------


def test_billets_directs_payes_statuts_et_taches(
    lieu, django_capture_on_commit_callbacks
):
    """
    P1 : deux tarifs du même événement réservés sans panier, puis payés.
    Après le retour de Stripe : paiement validé (`V`), les deux lignes validées (`V`),
    réservation payée (`P`), trois billets actifs (`K`). Tâches demandées : l'envoi des
    billets et le webhook de réservation tout de suite, puis l'envoi à l'ancien LaBoutik
    une fois par ligne, après la validation en base.
    La réservation reste `P` : elle ne passe `V` que quand la tâche d'envoi des billets
    tourne, et elle est seulement demandée ici.
    / P1: two prices booked without cart, then paid. Payment and lines VALID, reservation
    PAID, tickets NOT_SCANNED; mail + webhook tasks, then one LaBoutik sale per line.
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")
    tarif_reduit = ajouter_un_tarif(concert.produit, prix="5.00")

    reserver_des_billets_sans_panier(
        client, acheteur, concert.evenement, {concert.tarif: 2, tarif_reduit: 1}
    )
    reservation = Reservation.objects.get(
        user_commande=acheteur, event=concert.evenement
    )
    paiement = reservation.paiements.get()
    # On ne garde que les tâches demandées par le retour de paiement.
    # / Keep only the tasks requested by the payment return.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        revenir_de_stripe_billetterie(client, paiement)

    taches_du_retour = lieu.taches_demandees
    etat_attendu = {
        "paiement": Paiement_stripe.VALID,
        "lignes": [LigneArticle.VALID, LigneArticle.VALID],
        "reservations": [Reservation.PAID],
        "billets": [Ticket.NOT_SCANNED, Ticket.NOT_SCANNED, Ticket.NOT_SCANNED],
        "taches": [
            "webhook_reservation",
            "ticket_celery_mailer",
            "send_sale_to_laboutik",
            "send_sale_to_laboutik",
        ],
    }
    assert (
        etat_metier(
            paiement=paiement,
            reservations=[reservation],
            taches_demandees=taches_du_retour,
        )
        == etat_attendu
    )

    assert arguments_des_taches(taches_du_retour, "webhook_reservation") == [
        (reservation.pk,)
    ]
    assert arguments_des_taches(taches_du_retour, "ticket_celery_mailer") == [
        (reservation.pk,)
    ]

    # Une demande d'envoi à l'ancien LaBoutik par ligne de vente.
    # / One LaBoutik sale request per sale line.
    lignes_envoyees_a_laboutik = set()
    for arguments in arguments_des_taches(taches_du_retour, "send_sale_to_laboutik"):
        lignes_envoyees_a_laboutik.add(arguments[0])
    lignes_du_paiement = set()
    for ligne in LigneArticle.objects.filter(paiement_stripe=paiement):
        lignes_du_paiement.add(ligne.pk)
    assert lignes_envoyees_a_laboutik == lignes_du_paiement


# --------------------------------------------------------------------------
# P2 — Panier mixte payé en une fois
# / P2 — Mixed cart paid at once
# --------------------------------------------------------------------------


def test_panier_mixte_paye_une_seule_fois(lieu, django_capture_on_commit_callbacks):
    """
    P2 : un panier « adhésion 15 € + 2 billets de concert à 10 € + 1 billet de spectacle
    à 8 € + 1 h de ressource à 12 € + 1 réservation gratuite d'atelier », payé par UN seul
    paiement Stripe.
    Après le retour de Stripe : paiement validé, les quatre lignes validées, Commande payée,
    les trois réservations payées (`P`) — y compris celle de l'atelier gratuit, qui n'a
    aucune ligne de vente et n'est rattachée au paiement que par la Commande —, les quatre
    billets actifs, adhésion `ONCE` avec échéance, booking payé.
    L'ancien LaBoutik reçoit trois ventes (adhésion, concert, spectacle), toutes en
    « Stripe CB » (`SN`) et `V`. La ressource ne lui est pas envoyée.
    / P2: a mixed cart paid by ONE Stripe payment. Everything paid, including the free
    workshop reservation (linked to the payment only through the Order). Three LaBoutik
    sales (membership, concert, show), card, VALID; the resource is not sent.
    """
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00")
    concert = creer_evenement_avec_tarif(prix="10.00", jours_avant_l_evenement=7)
    spectacle = creer_evenement_avec_tarif(prix="8.00", jours_avant_l_evenement=9)
    atelier_gratuit = creer_evenement_avec_tarif(
        categorie=Product.FREERES, jours_avant_l_evenement=11
    )
    location = creer_ressource_avec_tarif(prix="12.00")

    panier = PanierSession(requete_avec_session(acheteur))
    panier.add_membership(adhesion.tarif.uuid)
    panier.add_ticket(concert.evenement.uuid, concert.tarif.uuid, qty=2)
    panier.add_ticket(spectacle.evenement.uuid, spectacle.tarif.uuid, qty=1)
    panier.add_ticket(atelier_gratuit.evenement.uuid, atelier_gratuit.tarif.uuid, qty=1)
    panier.add_resource(
        resource_uuid=location.ressource.pk,
        price_uuid=location.tarif.uuid,
        start_datetime=location.debut_du_creneau,
        slot_duration_minutes=60,
        slot_count=1,
    )
    # Même appel que la vue PanierMVT.checkout.
    # / Same call as the PanierMVT.checkout view.
    commande, _succes = CommandeService.materialiser(
        panier,
        acheteur,
        first_name=acheteur.first_name,
        last_name=acheteur.last_name,
        email=acheteur.email,
    )
    paiement = commande.paiement_stripe
    reservation_du_concert = commande.reservations.get(event=concert.evenement)
    reservation_du_spectacle = commande.reservations.get(event=spectacle.evenement)
    reservation_de_l_atelier = commande.reservations.get(
        event=atelier_gratuit.evenement
    )
    # On ne garde que les tâches demandées par le retour de paiement.
    # / Keep only the tasks requested by the payment return.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        revenir_de_stripe_billetterie(client_connecte(acheteur), paiement)

    taches_du_retour = lieu.taches_demandees
    etat_attendu = {
        "paiement": Paiement_stripe.VALID,
        "lignes": [
            LigneArticle.VALID,
            LigneArticle.VALID,
            LigneArticle.VALID,
            LigneArticle.VALID,
        ],
        "reservations": [Reservation.PAID, Reservation.PAID, Reservation.PAID],
        "billets": [
            Ticket.NOT_SCANNED,
            Ticket.NOT_SCANNED,
            Ticket.NOT_SCANNED,
            Ticket.NOT_SCANNED,
        ],
        "adhesion": Membership.ONCE,
        "adhesion_a_une_echeance": True,
        "booking": Booking.PAID_BY_USER,
        "commande": Commande.PAID,
    }
    assert (
        etat_metier(
            paiement=paiement,
            reservations=[
                reservation_du_concert,
                reservation_du_spectacle,
                reservation_de_l_atelier,
            ],
            adhesion=commande.memberships_commande.get(),
            booking=commande.bookings.get(),
            commande=commande,
        )
        == etat_attendu
    )

    # Un seul paiement Stripe pour toute la Commande.
    # / One single Stripe payment for the whole Order.
    assert lieu.stripe.mock_create.call_count == 1

    # Les tâches du retour, triées par nom : leur ordre suit l'ordre des lignes en base,
    # qui n'est pas garanti.
    # / The return's tasks, sorted by name: their order follows the database line order.
    # Adhésion : facture, récompense, webhook d'adhésion, envoi à LaBoutik.
    # Billets : un envoi à LaBoutik par ligne (concert, spectacle) ; un webhook et un
    # envoi de billets par réservation (concert, spectacle, atelier).
    # Ressource : rien.
    # / Membership: 4 tasks. Tickets: one LaBoutik sale per line, one webhook and one
    # ticket mail per reservation. Resource: nothing.
    assert sorted(noms_des_taches(taches_du_retour)) == [
        "refill_from_lespass_to_user_wallet_from_price_solded",
        "send_membership_invoice_to_email",
        "send_sale_to_laboutik",
        "send_sale_to_laboutik",
        "send_sale_to_laboutik",
        "ticket_celery_mailer",
        "ticket_celery_mailer",
        "ticket_celery_mailer",
        "webhook_membership",
        "webhook_reservation",
        "webhook_reservation",
        "webhook_reservation",
    ]

    # Charges utiles envoyées à l'ancien LaBoutik, triées par montant (centimes) :
    # spectacle 8 €, concert 2 × 10 €, adhésion 15 €.
    # / Payloads sent to legacy LaBoutik, sorted by amount (cents).
    assert charges_utiles_envoyees_a_laboutik(taches_du_retour) == [
        {
            "payment_method": PaymentMethod.STRIPE_NOFED,
            "amount": 800,
            "qty": "1.000000",
            "status": LigneArticle.VALID,
        },
        {
            "payment_method": PaymentMethod.STRIPE_NOFED,
            "amount": 1000,
            "qty": "2.000000",
            "status": LigneArticle.VALID,
        },
        {
            "payment_method": PaymentMethod.STRIPE_NOFED,
            "amount": 1500,
            "qty": "1.000000",
            "status": LigneArticle.VALID,
        },
    ]


# --------------------------------------------------------------------------
# T13 — Rejeu d'un paiement resté « payé » : l'avoir repasse « payé »
# / T13 — Replay of a payment left PAID: the credit note goes back to PAID
# --------------------------------------------------------------------------


def test_paiement_reste_paye_puis_rejeu_repasse_les_avoirs_en_paye(
    lieu, django_capture_on_commit_callbacks
):
    """
    Comportement actuel figé (voir T13, annexe machine à états §5) : c'est un défaut
    connu, à corriger dans un autre chantier (décision D33).
    Un paiement resté « payé » (`P`) porte une ligne de billet validée et un avoir émis
    dans l'admin (`N`). Le client rejoue le retour de Stripe (F5) : la transition
    `P → P` repasse « payée » TOUTE ligne du paiement qui n'est pas validée, avoir compris.
    Résultat figé : l'avoir est `P`, le paiement reste `P`, la réservation est de
    nouveau payée et ses billets renvoyés (webhook + mail redemandés).
    / Current behaviour frozen (T13, known defect, D33): a PAID-P replay turns the admin
    credit note back to PAID; the reservation is paid again and its tickets re-sent.
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")
    reserver_des_billets_sans_panier(
        client, acheteur, concert.evenement, {concert.tarif: 1}
    )
    reservation = Reservation.objects.get(
        user_commande=acheteur, event=concert.evenement
    )
    paiement = reservation.paiements.get()
    revenir_de_stripe_billetterie(client, paiement)
    ligne_du_billet = LigneArticle.objects.get(paiement_stripe=paiement)

    # ÉTAT DE DÉPART : le paiement est resté « payé » (`P`), sans traitement en cours.
    # En production, cela arrive quand une ligne du même paiement n'a pas de
    # déclencheur (annexe §2.2). Aucun formulaire du front ne produit ce cas
    # aujourd'hui : on le pose par `update()`, qui ne déclenche aucun signal
    # (tests/PIEGES.md 12.17).
    # / STARTING STATE: the payment stayed PAID. Set by update(), which fires no signal.
    Paiement_stripe.objects.filter(pk=paiement.pk).update(
        status=Paiement_stripe.PAID, traitement_en_cours=False
    )

    # L'admin émet un avoir sur la ligne du billet, par le bouton de l'admin : l'écran
    # s'ouvre (GET), puis il le valide (POST). Ligne payée par Stripe : pas de champ
    # « Remboursé par ».
    # / The admin issues a credit note on the ticket line: the screen opens (GET), then
    # is confirmed (POST). Stripe-paid line: no "Refunded by" field.
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    url_de_l_avoir = (
        f"/admin/BaseBillet/lignearticle/{ligne_du_billet.pk}/emettre_avoir/"
    )
    client_de_l_admin.get(url_de_l_avoir)
    reponse_de_l_admin = client_de_l_admin.post(url_de_l_avoir, {})
    assert reponse_de_l_admin.status_code == 302
    avoir = LigneArticle.objects.get(credit_note_for=ligne_du_billet)
    assert avoir.status == LigneArticle.CREDIT_NOTE
    # On ne garde que les tâches demandées par le rejeu.
    # / Keep only the tasks requested by the replay.
    lieu.taches_demandees.clear()

    # Le client recharge la page de retour de Stripe : `P → P`.
    # / The buyer reloads the Stripe return page: PAID -> PAID.
    with django_capture_on_commit_callbacks(execute=True):
        revenir_de_stripe_billetterie(client, paiement)

    taches_du_rejeu = lieu.taches_demandees
    etat_attendu = {
        "paiement": Paiement_stripe.PAID,
        # L'avoir est passé de `N` à `P` ; la ligne du billet reste `V`.
        # / The credit note went from N to P; the ticket line stays V.
        "lignes": [LigneArticle.PAID, LigneArticle.VALID],
        "reservations": [Reservation.PAID],
        "billets": [Ticket.NOT_SCANNED],
        "taches": ["webhook_reservation", "ticket_celery_mailer"],
    }
    assert (
        etat_metier(
            paiement=paiement,
            reservations=[reservation],
            taches_demandees=taches_du_rejeu,
        )
        == etat_attendu
    )

    avoir.refresh_from_db()
    assert avoir.status == LigneArticle.PAID


# --------------------------------------------------------------------------
# P2 — Adhésion seule, en ligne, sans panier
# / P2 — Membership alone, online, without cart
# --------------------------------------------------------------------------


def test_adhesion_en_ligne_payee(lieu, django_capture_on_commit_callbacks):
    """
    P2, adhésion seule : adhésion à 15 € prise sans panier, puis payée.
    Après le retour de Stripe : paiement et ligne validés, adhésion `ONCE` avec échéance,
    montant de la cotisation = prix du tarif vendu (15,00 €).
    Tâches : toutes après la validation en base (issue #117), dans l'ordre où elles
    sont enregistrées : le webhook d'adhésion, la facture par mail, la récompense
    monnaie et l'envoi à l'ancien LaBoutik.
    / P2 membership alone: paid, ONCE with a deadline, contribution = sold price.
    All tasks on commit (#117): membership webhook, invoice mail, reward, LaBoutik sale.
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="15.00")

    adherer_sans_panier(client, acheteur, adhesion.tarif)
    adhesion_creee = Membership.objects.get(user=acheteur, price=adhesion.tarif)
    paiement = adhesion_creee.stripe_paiement.get()
    # On ne garde que les tâches demandées par le retour de paiement.
    # / Keep only the tasks requested by the payment return.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        revenir_de_stripe_adhesion(client, paiement)

    taches_du_retour = lieu.taches_demandees
    etat_attendu = {
        "paiement": Paiement_stripe.VALID,
        "lignes": [LigneArticle.VALID],
        "adhesion": Membership.ONCE,
        "adhesion_a_une_echeance": True,
        # Toutes les tâches partent après la validation en base (issue #117), dans
        # l'ordre où elles sont enregistrées : le webhook d'adhésion (demandé par
        # l'enregistrement de l'échéance) passe donc avant la facture.
        # / Every task goes on commit (#117), in registration order: the webhook
        # (requested by the deadline save) comes before the invoice.
        "taches": [
            "webhook_membership",
            "send_membership_invoice_to_email",
            "refill_from_lespass_to_user_wallet_from_price_solded",
            "send_sale_to_laboutik",
        ],
    }
    assert (
        etat_metier(
            paiement=paiement,
            adhesion=adhesion_creee,
            taches_demandees=taches_du_retour,
        )
        == etat_attendu
    )

    ligne_de_l_adhesion = LigneArticle.objects.get(paiement_stripe=paiement)
    assert adhesion_creee.contribution_value == Decimal("15.00")
    assert adhesion_creee.contribution_value == ligne_de_l_adhesion.pricesold.prix

    assert arguments_des_taches(
        taches_du_retour, "send_membership_invoice_to_email"
    ) == [(str(adhesion_creee.uuid),)]
    assert arguments_des_taches(
        taches_du_retour, "refill_from_lespass_to_user_wallet_from_price_solded"
    ) == [(ligne_de_l_adhesion.pk,)]
    assert arguments_des_taches(taches_du_retour, "send_sale_to_laboutik") == [
        (ligne_de_l_adhesion.pk,)
    ]
    assert arguments_des_taches(taches_du_retour, "webhook_membership") == [
        (adhesion_creee.pk,)
    ]


# --------------------------------------------------------------------------
# P3 — Adhésion payée par prélèvement SEPA : en attente, puis refusé
# / P3 — Membership paid by SEPA debit: pending, then refused
# --------------------------------------------------------------------------


def preparer_une_adhesion_validee_par_l_admin():
    """
    ÉTAT DE DÉPART : une adhésion à validation manuelle (20 €), que l'admin a déjà
    validée (`ADMIN_VALID`). Son lien de paiement est actif.
    / STARTING STATE: a manually-validated membership the admin already validated.
    """
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="20.00", validation_manuelle=True)
    adhesion_validee = Membership.objects.create(
        user=acheteur,
        price=adhesion.tarif,
        status=Membership.ADMIN_VALID,
        contribution_value=Decimal("20.00"),
        first_name="Ada",
        last_name="Lovelace",
    )
    return adhesion_validee


def soumettre_un_prelevement_sepa(lieu, adhesion_validee):
    """
    Le client ouvre le lien de paiement de son adhésion validée, soumet un prélèvement
    SEPA, et Stripe envoie `checkout.session.completed` avec un paiement « pas encore
    payé » (le débit prend jusqu'à 14 jours).
    / The buyer opens the payment link, submits a SEPA debit, and Stripe sends
    `checkout.session.completed`, still unpaid.

    Rend un objet avec `paiement` et `identifiant_de_session`.
    """
    # Identifiant de session unique : le webhook retrouve le paiement par cet
    # identifiant, et la base de dev peut contenir d'autres sessions simulées.
    # / Unique session id: the webhook finds the payment by it.
    identifiant_de_session = f"cs_test_caracterisation_{identifiant_unique()}"
    lieu.stripe.session.id = identifiant_de_session

    # La session relue chez Stripe : formulaire soumis (`complete`), pas encore payé,
    # non expirée, moyen SEPA. Le paiement lié est un prélèvement SEPA.
    # / The session read back: submitted, unpaid, not expired, SEPA debit.
    champs_de_la_session = {
        "payment_method_types": ["card", "sepa_debit"],
        "payment_intent": "pi_test_caracterisation_sepa",
    }
    lieu.stripe.session.get = champs_de_la_session.get
    lieu.stripe.session.payment_status = "unpaid"
    lieu.stripe.session.status = "complete"
    lieu.stripe.session.expires_at = (timezone.now() + timedelta(hours=1)).timestamp()
    champs_du_paiement = {
        "payment_method_types": ["sepa_debit"],
        "payment_method_options": {"sepa_debit": {}},
    }
    lieu.stripe.pi.get = champs_du_paiement.get

    client_de_l_acheteur = client_connecte(adhesion_validee.user)
    client_de_l_acheteur.get(
        f"/memberships/{adhesion_validee.uuid}/get_checkout_for_membership/"
    )
    paiement = adhesion_validee.stripe_paiement.get()

    reponse_du_webhook = envoyer_un_evenement_stripe(
        "checkout.session.completed",
        objet_session_de_paiement(lieu, identifiant_de_session),
    )
    assert reponse_du_webhook.status_code == 200

    return SimpleNamespace(
        paiement=paiement,
        identifiant_de_session=identifiant_de_session,
    )


def test_sepa_soumis_statuts_et_mail_en_attente(
    lieu, django_capture_on_commit_callbacks
):
    """
    P3, prélèvement SEPA soumis : le paiement reste « en attente » (`W`), la ligne reste
    « non payée » (`U`), l'adhésion passe « paiement soumis » (`PP`, son lien de paiement
    ne recrée plus de checkout). Le webhook demande le mail « SEPA en attente », une fois,
    pour l'adhésion.
    Ce mail dépend du moyen posé sur le paiement (`Paiement_stripe.moyen`).
    / P3 SEPA submitted: payment PENDING, line UNPAID, membership PAYMENT_PENDING; the
    webhook requests the "SEPA pending" mail once (it depends on the payment's method).
    """
    adhesion_validee = preparer_une_adhesion_validee_par_l_admin()
    # On oublie les tâches demandées par la préparation (création du produit).
    # / Forget the tasks requested while preparing (product creation).
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        prelevement = soumettre_un_prelevement_sepa(lieu, adhesion_validee)

    etat_attendu = {
        "paiement": Paiement_stripe.PENDING,
        "lignes": [LigneArticle.UNPAID],
        "adhesion": Membership.PAYMENT_PENDING,
        "adhesion_a_une_echeance": False,
        "taches": ["send_membership_sepa_pending_user"],
    }
    assert (
        etat_metier(
            paiement=prelevement.paiement,
            adhesion=adhesion_validee,
            taches_demandees=lieu.taches_demandees,
        )
        == etat_attendu
    )

    assert arguments_des_taches(
        lieu.taches_demandees, "send_membership_sepa_pending_user"
    ) == [(str(adhesion_validee.uuid),)]


@pytest.mark.parametrize(
    "moyen_du_paiement, moyen_de_la_ligne, mail_attendu",
    [
        (PaymentMethod.STRIPE_SEPA_NOFED, PaymentMethod.STRIPE_NOFED, True),
        (PaymentMethod.STRIPE_NOFED, PaymentMethod.STRIPE_SEPA_NOFED, False),
    ],
    ids=["paiement_sepa_ligne_carte", "paiement_carte_ligne_sepa"],
)
def test_mail_sepa_en_attente_lu_sur_le_moyen_du_paiement(
    lieu,
    django_capture_on_commit_callbacks,
    moyen_du_paiement,
    moyen_de_la_ligne,
    mail_attendu,
):
    """
    Le mail « SEPA en attente » suit le moyen du PAIEMENT (`Paiement_stripe.moyen`),
    jamais celui de sa ligne. La relecture de la session Stripe est simulée : elle pose
    le paiement « en attente » avec un moyen, et la ligne avec un AUTRE moyen.
    - paiement SEPA, ligne carte : le mail part ;
    - paiement carte, ligne SEPA : le mail ne part pas.
    / The "SEPA pending" mail follows the payment's method, never its line's.
    """
    adhesion_validee = preparer_une_adhesion_validee_par_l_admin()
    identifiant_de_session = f"cs_test_caracterisation_{identifiant_unique()}"
    lieu.stripe.session.id = identifiant_de_session
    client_de_l_acheteur = client_connecte(adhesion_validee.user)
    client_de_l_acheteur.get(
        f"/memberships/{adhesion_validee.uuid}/get_checkout_for_membership/"
    )
    lieu.taches_demandees.clear()

    def relecture_simulee_de_la_session(paiement):
        # Le paiement en attente avec son moyen, sa ligne avec un autre moyen.
        # / The pending payment with its method, its line with another method.
        Paiement_stripe.objects.filter(pk=paiement.pk).update(
            status=Paiement_stripe.PENDING, moyen=moyen_du_paiement
        )
        paiement.lignearticles.update(payment_method=moyen_de_la_ligne)
        return Paiement_stripe.PENDING

    with patch.object(
        Paiement_stripe,
        "update_checkout_status",
        autospec=True,
        side_effect=relecture_simulee_de_la_session,
    ):
        with django_capture_on_commit_callbacks(execute=True):
            reponse_du_webhook = envoyer_un_evenement_stripe(
                "checkout.session.completed",
                objet_session_de_paiement(lieu, identifiant_de_session),
            )

    assert reponse_du_webhook.status_code == 200
    mails_sepa_demandes = arguments_des_taches(
        lieu.taches_demandees, "send_membership_sepa_pending_user"
    )
    if mail_attendu:
        assert mails_sepa_demandes == [(str(adhesion_validee.uuid),)]
    else:
        assert mails_sepa_demandes == []


def test_sepa_refuse_lignes_en_echec_adhesion_rearmee(
    lieu, django_capture_on_commit_callbacks
):
    """
    P3, prélèvement SEPA refusé : après `checkout.session.async_payment_failed`, le
    paiement est « échoué » (`F`), la ligne « échouée » (`D`), et l'adhésion revient
    « validée par l'admin » (`AV`) : son lien de paiement remarche. Le webhook demande le
    mail « paiement refusé », une fois, pour le paiement.
    Le passage `W → F` ne déclenche aucune transition (voir T5).
    / P3 SEPA refused: payment FAILED, line FAILED, membership back to ADMIN_VALID;
    "payment refused" mail requested once. W -> F fires no transition (T5).
    """
    adhesion_validee = preparer_une_adhesion_validee_par_l_admin()
    # On oublie les tâches demandées par la préparation (création du produit).
    # / Forget the tasks requested while preparing (product creation).
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        prelevement = soumettre_un_prelevement_sepa(lieu, adhesion_validee)
        reponse_du_webhook = envoyer_un_evenement_stripe(
            "checkout.session.async_payment_failed",
            objet_session_de_paiement(lieu, prelevement.identifiant_de_session),
        )
    assert reponse_du_webhook.status_code == 200

    etat_attendu = {
        "paiement": Paiement_stripe.FAILED,
        "lignes": [LigneArticle.FAILED],
        "adhesion": Membership.ADMIN_VALID,
        "adhesion_a_une_echeance": False,
        "taches": ["send_membership_sepa_pending_user", "send_payment_refused_user"],
    }
    assert (
        etat_metier(
            paiement=prelevement.paiement,
            adhesion=adhesion_validee,
            taches_demandees=lieu.taches_demandees,
        )
        == etat_attendu
    )

    assert arguments_des_taches(lieu.taches_demandees, "send_payment_refused_user") == [
        (str(prelevement.paiement.uuid),)
    ]


# --------------------------------------------------------------------------
# P15 — Renouvellement d'un abonnement (`invoice.paid`)
# / P15 — Subscription renewal (`invoice.paid`)
# --------------------------------------------------------------------------


def test_renouvellement_abonnement_iteration_et_statut_auto(
    lieu, django_capture_on_commit_callbacks
):
    """
    P15 : Stripe prélève la deuxième échéance d'un abonnement et envoie `invoice.paid`.
    Un nouveau paiement (source « facture ») et une nouvelle ligne sont créés, puis validés
    (`V`). L'adhésion reste « abonnement automatique » (`AUTO`), avec une échéance ; son
    compteur d'échéances passe de 1 à 2 ; la dernière facture connue devient la nouvelle.
    Tâches : comme une adhésion en ligne (webhook, facture, récompense, LaBoutik), mais
    avec DEUX webhooks d'adhésion.
    / P15: renewal invoice paid. New payment and line VALID, membership AUTO, iteration
    1 -> 2, last invoice updated; online-membership tasks, with TWO membership webhooks.
    """
    acheteur = creer_utilisateur()
    adhesion = creer_adhesion(prix="15.00", recurrente=True)
    identifiant_de_l_abonnement = f"sub_test_{identifiant_unique()}"
    identifiant_de_la_nouvelle_facture = f"in_test_{identifiant_unique()}"

    # ÉTAT DE DÉPART : un abonnement en cours, première échéance payée.
    # / STARTING STATE: a running subscription, first instalment paid.
    adhesion_abonnee = Membership.objects.create(
        user=acheteur,
        price=adhesion.tarif,
        status=Membership.AUTO,
        contribution_value=Decimal("15.00"),
        first_name="Ada",
        last_name="Lovelace",
        stripe_id_subscription=identifiant_de_l_abonnement,
        last_stripe_invoice="in_test_premiere_echeance",
        current_iteration=1,
        deadline=timezone.now() + timedelta(days=2),
    )

    # La facture relue chez Stripe : payée, une ligne de 15 € (en centimes).
    # / The invoice read back at Stripe: paid, one 15 € line (in cents).
    facture_stripe_simulee = SimpleNamespace(
        id=identifiant_de_la_nouvelle_facture,
        status="paid",
        # Une vraie facture Stripe porte toujours `amount_paid` : il est lu comme le
        # montant encaissé du paiement de l'échéance.
        # / A real Stripe invoice always carries `amount_paid`, read as the collected amount.
        amount_paid=1500,
        lines={"data": [SimpleNamespace(amount=1500, quantity=1)]},
        parent=SimpleNamespace(
            subscription_details=SimpleNamespace(
                subscription=identifiant_de_l_abonnement
            )
        ),
    )
    evenement_facture_payee = {
        "id": identifiant_de_la_nouvelle_facture,
        "billing_reason": "subscription_cycle",
        "paid": True,
        "subscription": identifiant_de_l_abonnement,
        "subscription_details": {
            "metadata": {
                "tenant": str(lieu.tenant.uuid),
                "membership_uuid": str(adhesion_abonnee.uuid),
                "price_uuid": str(adhesion.tarif.uuid),
            }
        },
        "metadata": {},
    }
    # On oublie les tâches demandées par la préparation (produit, adhésion).
    # / Forget the tasks requested while preparing (product, membership).
    lieu.taches_demandees.clear()

    with patch("stripe.Invoice.retrieve", return_value=facture_stripe_simulee):
        with django_capture_on_commit_callbacks(execute=True):
            reponse_du_webhook = envoyer_un_evenement_stripe(
                "invoice.paid", evenement_facture_payee
            )

    assert reponse_du_webhook.status_code == 202
    nouveau_paiement = Paiement_stripe.objects.get(
        invoice_stripe=identifiant_de_la_nouvelle_facture
    )
    etat_attendu = {
        "paiement": Paiement_stripe.VALID,
        "lignes": [LigneArticle.VALID],
        "adhesion": Membership.AUTO,
        "adhesion_a_une_echeance": True,
        # Deux webhooks d'adhésion : l'adhésion a déjà une échéance, et elle est
        # enregistrée deux fois (mise à jour après paiement, puis nouvelle échéance).
        # Chaque enregistrement d'une adhésion avec échéance en demande un.
        # Toutes les tâches partent après la validation en base (issue #117), dans
        # l'ordre où elles sont enregistrées : les deux webhooks passent avant la facture.
        # / Two membership webhooks: saved twice while it already has a deadline.
        # Every task goes on commit (#117), in registration order: webhooks first.
        "taches": [
            "webhook_membership",
            "webhook_membership",
            "send_membership_invoice_to_email",
            "refill_from_lespass_to_user_wallet_from_price_solded",
            "send_sale_to_laboutik",
        ],
    }
    assert (
        etat_metier(
            paiement=nouveau_paiement,
            adhesion=adhesion_abonnee,
            taches_demandees=lieu.taches_demandees,
        )
        == etat_attendu
    )

    assert nouveau_paiement.source == Paiement_stripe.INVOICE
    assert adhesion_abonnee.current_iteration == 2
    assert adhesion_abonnee.last_stripe_invoice == identifiant_de_la_nouvelle_facture
    assert adhesion_abonnee.contribution_value == Decimal("15.00")
