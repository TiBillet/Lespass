"""
Tests de caractérisation : les ventes faites dans l'ADMIN et par l'API v2 (parcours P13,
P16), et la décision « Stripe ou gratuit » (trou T21).
/ Characterization tests: sales made in the ADMIN and through API v2 (flows P13, P16),
and the "Stripe or free" decision (gap T21).

LOCALISATION : tests/pytest/test_caracterisation_admin_api.py

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
- les statuts finaux, relus en base : lignes de vente, réservations, billets, adhésion,
  booking ;
- les créations de session de paiement Stripe (simulées) : leur nombre ;
- les appels à Fedow (simulé) pour la recharge cadeau, et les réponses de l'API ;
- les tâches Celery demandées : leur nom et leurs arguments ;
- la charge utile envoyée à l'ancien LaBoutik (`LigneArticleSerializer`).
Ils ne lisent JAMAIS directement sur la ligne un champ que le chantier retire
(`payment_method`, `asset`, `idempotency_key`…) : c'est la charge utile, la réponse
de l'API ou l'appel à Fedow qui fait contrat.
/ They only read final statuses, Stripe session creations, Fedow calls and API
responses, requested Celery tasks and the legacy LaBoutik payload.

CODE PARCOURU / CODE EXERCISED
- Administration/admin_tenant.py — MembershipAddForm (ajout d'une adhésion),
  ReservationAddAdmin (vente de billets dans l'admin) ;
- BaseBillet/signals.py — create_lignearticle_if_membership_created_on_admin ;
- BaseBillet/triggers.py — trigger_A (adhésion), trigger_B (billet) ;
- api_v2/views.py — WalletRefillViewSet (recharge cadeau, clé d'idempotence) ;
- BaseBillet/validators.py — TicketCreator (billets : Stripe ou gratuit) ;
- booking/booking_engine.py — validate_new_booking, Booking.to_pay (ressource : Stripe
  ou gratuit).

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin, rien ne reste
en base de dev. Stripe (session, catalogue), Fedow et Celery sont simulés : aucun appel
réseau, aucune tâche envoyée au worker. Les tâches lancées en `transaction.on_commit`
sont exécutées par `django_capture_on_commit_callbacks(execute=True)` (tests/PIEGES.md 13.14).
/ Rolled-back transaction per test. Stripe, Fedow and Celery are faked.

L'assistant `etat_metier()` et les gestes d'achat en ligne viennent du premier fichier
de caractérisation, `test_caracterisation_en_ligne.py`.
/ `etat_metier()` and the online buying helpers come from the first characterization file.

Lancer / Run : make test ARGS="tests/pytest/test_caracterisation_admin_api.py"
"""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from AuthBillet.models import Wallet
from BaseBillet.models import (
    ExternalApiKey,
    LigneArticle,
    Membership,
    PaymentMethod,
    Reservation,
    Ticket,
)
from booking.models import Booking
from fabriques_panier import (
    catalogue_stripe_simule,
    client_connecte,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_ressource_avec_tarif,
    creer_utilisateur,
    identifiant_unique,
    taches_celery_enregistrees,
)
from fedow_public.models import AssetFedowPublic
from rest_framework_api_key.models import APIKey
from test_caracterisation_en_ligne import (
    EN_TETE_HTMX,
    arguments_des_taches,
    charges_utiles_envoyees_a_laboutik,
    creer_un_administrateur_du_lieu,
    etat_metier,
    reserver_des_billets_sans_panier,
)

pytestmark = pytest.mark.django_db

# Adresse de la recharge cadeau de l'API v2 (api_v2/urls.py).
# / API v2 gift refill address.
URL_DE_LA_RECHARGE_CADEAU = "/api/v2/wallet-refills/"


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
# Assistants de lecture
# / Reading helpers
# --------------------------------------------------------------------------


def statuts_des_lignes_de_l_adhesion(adhesion):
    """
    Les statuts des lignes de vente rattachées à l'adhésion, triés.
    Sert aux ventes sans paiement Stripe (admin), que `etat_metier` ne lit pas.
    / Sorted statuses of the sale lines linked to the membership (non-Stripe sales).
    """
    statuts_des_lignes = []
    for ligne in LigneArticle.objects.filter(membership=adhesion):
        statuts_des_lignes.append(ligne.status)
    return sorted(statuts_des_lignes)


def statuts_des_lignes_de_la_reservation(reservation):
    """Les statuts des lignes de vente rattachées à la réservation, triés.
    / Sorted statuses of the sale lines linked to the reservation."""
    statuts_des_lignes = []
    for ligne in LigneArticle.objects.filter(reservation=reservation):
        statuts_des_lignes.append(ligne.status)
    return sorted(statuts_des_lignes)


def statuts_des_lignes_du_booking(booking):
    """Les statuts des lignes de vente rattachées à la réservation de ressource, triés.
    / Sorted statuses of the sale lines linked to the resource booking."""
    statuts_des_lignes = []
    for ligne in LigneArticle.objects.filter(booking=booking):
        statuts_des_lignes.append(ligne.status)
    return sorted(statuts_des_lignes)


def lignes_de_recharge_de_la_monnaie(monnaie_cadeau):
    """
    Les lignes de vente « recharge cadeau » de cette monnaie.
    La vue range chaque recharge sous un produit dédié à la monnaie, nommé
    « Recharge <nom de la monnaie> » (api_v2/views.py, `_creer_ligne_article_recharge`).
    On passe par ce produit : la clé d'idempotence est une colonne que le chantier retire.
    / The gift refill sale lines of this currency, found through the per-currency
    product (the idempotency key is a column the chantier removes).
    """
    return LigneArticle.objects.filter(
        pricesold__productsold__product__name=f"Recharge {monnaie_cadeau.name}"
    )


# --------------------------------------------------------------------------
# Gestes de l'admin, du partenaire API et de l'acheteur
# / Admin, API partner and buyer actions
# --------------------------------------------------------------------------


def creer_une_adhesion_depuis_l_admin(
    client_de_l_admin, email, tarif, contribution, moyen_de_paiement
):
    """
    L'admin remplit le formulaire « Ajouter une adhésion » et l'enregistre.
    / The admin fills in the "Add membership" form and saves it.

    Le formulaire demande à Fedow le portefeuille de la personne (`clean_email`), en HTTP.
    Fedow est simulé le temps de l'envoi : aucun appel réseau.
    Les quatre champs `lignearticles-*` sont le formulaire vide de la liste des ventes,
    affichée sous l'adhésion : l'admin Django l'exige même sans ligne saisie.
    / The form asks Fedow for the person's wallet over HTTP: Fedow is faked. The four
    `lignearticles-*` fields are the empty inline management form, required by the admin.
    """
    donnees_du_formulaire = {
        "email": email,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "price": str(tarif.pk),
        "contribution": contribution,
        "payment_method": moyen_de_paiement,
        "card_number": "",
        "lignearticles-TOTAL_FORMS": "0",
        "lignearticles-INITIAL_FORMS": "0",
        "lignearticles-MIN_NUM_FORMS": "0",
        "lignearticles-MAX_NUM_FORMS": "1000",
    }
    with patch("Administration.admin_tenant.FedowAPI"):
        return client_de_l_admin.post(
            "/admin/BaseBillet/membership/add/", donnees_du_formulaire
        )


def vendre_des_billets_depuis_l_admin(
    client_de_l_admin, email, billetterie, quantite, moyen_de_paiement
):
    """
    L'admin remplit le formulaire « Ajouter une réservation » : un tarif d'un événement,
    une quantité, un moyen de paiement, sans « prix par billet » (le prix du tarif sert).
    / The admin fills in the "Add reservation" form: one event price, a quantity, a
    payment method, no per-ticket price (the rate's price is used).
    """
    donnees_du_formulaire = {
        "email": email,
        "price": f"{billetterie.evenement.uuid}:{billetterie.tarif.uuid}",
        "amount": "",
        "payment_method": moyen_de_paiement,
        "quantity": str(quantite),
    }
    return client_de_l_admin.post(
        "/admin/BaseBillet/reservation/add/", donnees_du_formulaire
    )


def creer_une_cle_api_de_recharge_cadeau(lieu):
    """
    Une monnaie cadeau du lieu (catégorie « jeton local non adossé à l'euro ») et une clé
    API v2 autorisée à la recharger.
    / A gift currency of the venue and an API v2 key allowed to top it up.

    Rend un objet avec `cle` (le texte à mettre dans l'en-tête) et `monnaie_cadeau`.
    """
    portefeuille_du_lieu = Wallet.objects.create(origin=lieu.tenant)
    monnaie_cadeau = AssetFedowPublic.objects.create(
        name=f"TEST_caracterisation cadeau {identifiant_unique()}",
        currency_code="TGC",
        wallet_origin=portefeuille_du_lieu,
        origin=lieu.tenant,
        category=AssetFedowPublic.TOKEN_LOCAL_NOT_FIAT,
    )
    cle_api, texte_de_la_cle = APIKey.objects.create_key(
        name=f"TEST_caracterisation {identifiant_unique()}"
    )
    ExternalApiKey.objects.create(
        name=f"TEST_caracterisation {identifiant_unique()}",
        key=cle_api,
        gift_asset=monnaie_cadeau,
    )
    return SimpleNamespace(cle=texte_de_la_cle, monnaie_cadeau=monnaie_cadeau)


def demander_une_recharge_cadeau(cle_api, destinataire, montant, cle_d_idempotence):
    """
    Le partenaire appelle l'API v2 pour offrir `montant` jetons cadeau à `destinataire`,
    avec sa clé d'idempotence (en-tête `Idempotency-Key`).
    / The partner calls API v2 to give `montant` gift tokens, with its idempotency key.
    """
    client_du_partenaire = APIClient()
    return client_du_partenaire.post(
        URL_DE_LA_RECHARGE_CADEAU,
        data={
            "email": destinataire.email,
            "asset": str(cle_api.monnaie_cadeau.uuid),
            "amount": montant,
        },
        format="json",
        SERVER_NAME="lespass.tibillet.localhost",
        HTTP_AUTHORIZATION=f"Api-Key {cle_api.cle}",
        HTTP_IDEMPOTENCY_KEY=cle_d_idempotence,
    )


def reserver_une_ressource_sans_panier(client, location):
    """
    Réserve un créneau d'une heure de la ressource par son formulaire, sans panier.
    Le formulaire envoie des dates sans fuseau, lues dans le fuseau du lieu
    (tests/PIEGES.md 13.18).
    / Books a one-hour slot through the resource form, without cart.
    """
    debut_du_creneau = location.debut_du_creneau
    fin_du_creneau = debut_du_creneau + timedelta(hours=1)
    donnees_du_formulaire = {
        "resource": str(location.ressource.pk),
        "price_uuid": str(location.tarif.uuid),
        "start_datetime": debut_du_creneau.replace(tzinfo=None).isoformat(),
        "end_time": fin_du_creneau.replace(tzinfo=None).isoformat(),
        "firstname": "Ada",
        "lastname": "Lovelace",
    }
    return client.post(
        f"/booking/{location.ressource.pk}/book/",
        donnees_du_formulaire,
        **EN_TETE_HTMX,
    )


# --------------------------------------------------------------------------
# P16 — Adhésion créée dans l'admin
# / P16 — Membership created in the admin
# --------------------------------------------------------------------------


def test_adhesion_creee_dans_l_admin_passe_par_trigger_a(
    lieu, django_capture_on_commit_callbacks
):
    """
    P16 : l'admin ajoute une adhésion de 20 €, payée en espèces.
    L'adhésion reste « créée dans l'admin » (`D`) et reçoit une échéance. Une ligne de
    vente est créée, puis passe « payée » : `trigger_A` la valide (`V`).
    Tâches : la facture par mail tout de suite ; puis, après la validation en base, le
    mail de connexion de l'adhérente (son adresse n'est pas encore confirmée), la
    récompense monnaie, l'envoi à l'ancien LaBoutik, et DEUX webhooks d'adhésion.
    L'ancien LaBoutik reçoit la vente en espèces (`CA`), 2000 centimes.
    / P16: the admin adds a 20 € cash membership. It stays ADMIN with a deadline; its sale
    line goes PAID then VALID through trigger_A. Invoice mail at once; then login mail,
    reward, LaBoutik sale and TWO membership webhooks on commit.
    """
    adhesion = creer_adhesion(prix="20.00")
    adherente = creer_utilisateur()
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    # On oublie les tâches demandées par la préparation (produit, utilisateurs).
    # / Forget the tasks requested while preparing (product, users).
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = creer_une_adhesion_depuis_l_admin(
            client_de_l_admin,
            email=adherente.email,
            tarif=adhesion.tarif,
            contribution="20",
            moyen_de_paiement=PaymentMethod.CASH,
        )

    # Succès de l'admin : redirection vers la liste (302). Un 200 = formulaire en erreur.
    # / Admin success = redirect (302). A 200 means form errors.
    assert reponse.status_code == 302
    adhesion_creee = Membership.objects.get(user=adherente, price=adhesion.tarif)
    taches_de_l_admin = lieu.taches_demandees
    etat_attendu = {
        "adhesion": Membership.ADMIN,
        "adhesion_a_une_echeance": True,
        # Deux webhooks d'adhésion : l'échéance est posée par `trigger_A`, qui enregistre
        # l'adhésion (premier webhook), puis la création de l'adhésion finit, avec son
        # échéance (second webhook). Chaque enregistrement d'une adhésion avec échéance
        # en demande un.
        # / Two membership webhooks: trigger_A saves the membership with its deadline,
        # then the creation save finishes with the deadline set.
        "taches": [
            "send_membership_invoice_to_email",
            "connexion_celery_mailer",
            "webhook_membership",
            "refill_from_lespass_to_user_wallet_from_price_solded",
            "send_sale_to_laboutik",
            "webhook_membership",
        ],
    }
    assert (
        etat_metier(adhesion=adhesion_creee, taches_demandees=taches_de_l_admin)
        == etat_attendu
    )
    assert statuts_des_lignes_de_l_adhesion(adhesion_creee) == [LigneArticle.VALID]

    ligne_de_l_adhesion = LigneArticle.objects.get(membership=adhesion_creee)
    assert arguments_des_taches(
        taches_de_l_admin, "send_membership_invoice_to_email"
    ) == [(str(adhesion_creee.uuid),)]
    assert arguments_des_taches(
        taches_de_l_admin, "refill_from_lespass_to_user_wallet_from_price_solded"
    ) == [(ligne_de_l_adhesion.pk,)]
    assert arguments_des_taches(taches_de_l_admin, "webhook_membership") == [
        (adhesion_creee.pk,),
        (adhesion_creee.pk,),
    ]

    assert charges_utiles_envoyees_a_laboutik(taches_de_l_admin) == [
        {
            "payment_method": PaymentMethod.CASH,
            "amount": 2000,
            "qty": "1.000000",
            "status": LigneArticle.VALID,
        },
    ]


# --------------------------------------------------------------------------
# P16 / T12 — Billets vendus dans l'admin, offerts
# / P16 / T12 — Tickets sold in the admin, offered
# --------------------------------------------------------------------------


def test_billets_vendus_dans_l_admin_offert_au_prix_part_offerte_totale(
    lieu, django_capture_on_commit_callbacks
):
    """
    P16 / T12 : l'admin vend deux billets d'un tarif à 15 € et choisit « Offert ».
    La réservation est créée validée (`V`), ses deux billets actifs (`K`), et UNE ligne
    de vente validée (`V`), de quantité 2. Le billet offert est écrit comme un offert de
    la caisse (décision D32) : au prix du tarif (1500 centimes l'unité), avec une part
    offerte égale à son total (3000) ; son net vendu vaut 0.
    Tâche : l'envoi des billets par mail, seulement. Une vente faite dans l'admin n'est
    pas envoyée à l'ancienne caisse LaBoutik (décision du mainteneur, D-2b).
    / P16/T12: 2 tickets of a 15 € price sold as "Offered" in the admin: reservation and
    line VALID, tickets NOT_SCANNED. Written like a register gift (D32): unit price 1500,
    offered part = total (3000), net 0. Only the tickets mail; nothing sent to the legacy
    LaBoutik.
    """
    concert = creer_evenement_avec_tarif(prix="15.00")
    email_de_l_acheteur = f"test+caracterisation{identifiant_unique()}@mock.test"
    client_de_l_admin = creer_un_administrateur_du_lieu(lieu)
    # On oublie les tâches demandées par la préparation.
    # / Forget the tasks requested while preparing.
    lieu.taches_demandees.clear()

    with django_capture_on_commit_callbacks(execute=True):
        reponse = vendre_des_billets_depuis_l_admin(
            client_de_l_admin,
            email=email_de_l_acheteur,
            billetterie=concert,
            quantite=2,
            moyen_de_paiement=PaymentMethod.FREE,
        )

    # Succès de l'admin : redirection vers la liste (302). Un 200 = formulaire en erreur.
    # / Admin success = redirect (302). A 200 means form errors.
    assert reponse.status_code == 302
    reservation = Reservation.objects.get(
        user_commande__email=email_de_l_acheteur, event=concert.evenement
    )
    taches_de_l_admin = lieu.taches_demandees
    etat_attendu = {
        "reservations": [Reservation.VALID],
        "billets": [Ticket.NOT_SCANNED, Ticket.NOT_SCANNED],
        "taches": ["ticket_celery_mailer"],
    }
    assert (
        etat_metier(reservations=[reservation], taches_demandees=taches_de_l_admin)
        == etat_attendu
    )
    assert statuts_des_lignes_de_la_reservation(reservation) == [LigneArticle.VALID]

    ligne_de_la_vente = LigneArticle.objects.get(reservation=reservation)
    assert arguments_des_taches(taches_de_l_admin, "ticket_celery_mailer") == [
        (reservation.pk,)
    ]

    # Le cœur du test : prix du tarif écrit, part offerte = total, net 0.
    # / The heart of the test: rate's price written, offered part = total, net 0.
    assert ligne_de_la_vente.total_catalogue == 3000
    assert ligne_de_la_vente.part_offerte == 3000
    assert ligne_de_la_vente.total_ttc == 0


# --------------------------------------------------------------------------
# P13 — Recharge cadeau par l'API v2 : échec de Fedow, puis nouvel essai
# / P13 — Gift refill through API v2: Fedow failure, then retry
# --------------------------------------------------------------------------


def test_recharge_api_v2_echec_puis_nouvel_essai_meme_ligne(lieu):
    """
    P13 : un partenaire demande une recharge cadeau de 300 jetons, avec sa clé
    d'idempotence. Il envoie trois fois la même demande :
    1. Fedow est en panne : réponse 502, la ligne de vente passe « échouée » (`D`) ;
    2. nouvel essai, même clé, Fedow répond : réponse 201, la MÊME ligne repasse « créée »
       (`O`) pendant l'appel à Fedow, puis « validée » (`V`) ;
    3. rejeu après le succès : réponse 208, identique à la réponse 201, sans appel à Fedow.
    Une seule ligne de vente pour les trois demandes ; Fedow est appelé deux fois, avec
    la même ligne.
    / P13: same gift refill sent three times with one idempotency key. Fedow down: 502,
    line FAILED. Retry: the SAME line goes CREATED during the Fedow call, then VALID, 201.
    Replay: 208, same body, no Fedow call. One single line; Fedow called twice.
    """
    destinataire = creer_utilisateur()
    cle_api = creer_une_cle_api_de_recharge_cadeau(lieu)
    cle_d_idempotence = f"caracterisation-{uuid.uuid4().hex}"
    identifiant_de_la_transaction_fedow = str(uuid.uuid4())

    # Fedow simulé : chaque appel note la ligne de vente qu'il reçoit (dans ses
    # métadonnées) et le statut de cette ligne au moment de l'appel.
    # / Faked Fedow: each call records the sale line it receives and its status then.
    lignes_vues_par_fedow = []

    def noter_la_ligne_recue_par_fedow(metadata):
        ligne_recue = LigneArticle.objects.get(uuid=metadata["ligne_article_uuid"])
        lignes_vues_par_fedow.append((ligne_recue.uuid, ligne_recue.status))

    def fedow_en_panne(user, amount, asset, metadata):
        noter_la_ligne_recue_par_fedow(metadata)
        raise ConnectionError("Fedow ne répond pas")

    def fedow_disponible(user, amount, asset, metadata):
        noter_la_ligne_recue_par_fedow(metadata)
        return {"uuid": identifiant_de_la_transaction_fedow}

    with (
        patch("fedow_connect.models.FedowConfig.can_fedow", return_value=True),
        patch("fedow_connect.fedow_api.FedowAPI") as fedow_simule,
    ):
        recharger_la_tirelire = (
            fedow_simule.return_value.transaction.refill_from_lespass_to_user_wallet
        )

        # 1. Fedow en panne.
        # / 1. Fedow down.
        recharger_la_tirelire.side_effect = fedow_en_panne
        reponse_du_premier_essai = demander_une_recharge_cadeau(
            cle_api, destinataire, 300, cle_d_idempotence
        )
        assert reponse_du_premier_essai.status_code == 502
        ligne_de_recharge = lignes_de_recharge_de_la_monnaie(
            cle_api.monnaie_cadeau
        ).get()
        assert ligne_de_recharge.status == LigneArticle.FAILED

        # 2. Nouvel essai avec la même clé : Fedow répond.
        # / 2. Retry with the same key: Fedow answers.
        recharger_la_tirelire.side_effect = fedow_disponible
        reponse_du_nouvel_essai = demander_une_recharge_cadeau(
            cle_api, destinataire, 300, cle_d_idempotence
        )

        # 3. Rejeu après le succès.
        # / 3. Replay after success.
        reponse_du_rejeu = demander_une_recharge_cadeau(
            cle_api, destinataire, 300, cle_d_idempotence
        )

    assert reponse_du_nouvel_essai.status_code == 201
    reponse_attendue = {
        "@context": "https://schema.org",
        "@type": "MoneyTransfer",
        "identifier": identifiant_de_la_transaction_fedow,
        "amount": 300,
        "asset": str(cle_api.monnaie_cadeau.uuid),
        "recipient": {"@type": "Person", "email": destinataire.email},
    }
    assert reponse_du_nouvel_essai.json() == reponse_attendue

    # Le rejeu rend la même réponse, reconstruite depuis la ligne, sans appeler Fedow.
    # / The replay returns the same body, rebuilt from the line, without calling Fedow.
    assert reponse_du_rejeu.status_code == 208
    assert reponse_du_rejeu.json() == reponse_attendue

    # Une seule ligne pour les trois demandes, validée à la fin.
    # / One single line for the three requests, VALID at the end.
    lignes_de_recharge = lignes_de_recharge_de_la_monnaie(cle_api.monnaie_cadeau)
    assert lignes_de_recharge.count() == 1
    ligne_de_recharge.refresh_from_db()
    assert ligne_de_recharge.status == LigneArticle.VALID

    # Fedow a reçu deux fois la MÊME ligne, « créée » (`O`) à chaque appel.
    # / Fedow received the SAME line twice, CREATED at each call.
    assert lignes_vues_par_fedow == [
        (ligne_de_recharge.uuid, LigneArticle.CREATED),
        (ligne_de_recharge.uuid, LigneArticle.CREATED),
    ]


# --------------------------------------------------------------------------
# T21 — La décision « Stripe ou gratuit » : billets et ressource
# / T21 — The "Stripe or free" decision: tickets and resource
# --------------------------------------------------------------------------


def test_decision_stripe_ou_gratuit_billets_et_booking(lieu):
    """
    T21 : le choix entre « paiement Stripe » et « validation gratuite » se fait sur le
    total à payer (montant × quantité des lignes), sans panier :
    - billets (`TicketCreator`) : 2 billets à 10 € → UNE session Stripe, réservation
      « non payée » (`U`), billets inactifs (`N`), ligne « non payée » (`U`) ; 1 billet à 0 € → aucune session,
      réservation gratuite validée (`FA`, compte actif), ligne validée (`V`) ;
    - ressource (`Booking.to_pay`) : 1 h à 12 € → UNE session Stripe, booking « en attente
      de paiement » (`WP`), ligne « non payée » (`U`) ; 1 h à 0 € → aucune session,
      booking gratuit validé (`FU`, compte actif), ligne validée (`V`).
    / T21: the Stripe-or-free choice is made on the total (amount x quantity), without
    cart: paid tickets and paid slot -> one Stripe session each; 0 € ticket and 0 € slot
    -> no session, free validation.
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert_payant = creer_evenement_avec_tarif(prix="10.00", jours_avant_l_evenement=7)
    concert_a_zero_euro = creer_evenement_avec_tarif(
        prix="0.00", jours_avant_l_evenement=9
    )
    location_payante = creer_ressource_avec_tarif(prix="12.00")
    location_a_zero_euro = creer_ressource_avec_tarif(prix="0.00")

    # Billets payants : une session Stripe.
    # / Paid tickets: one Stripe session.
    reserver_des_billets_sans_panier(
        client, acheteur, concert_payant.evenement, {concert_payant.tarif: 2}
    )
    reservation_payante = Reservation.objects.get(
        user_commande=acheteur, event=concert_payant.evenement
    )
    assert lieu.stripe.mock_create.call_count == 1
    assert etat_metier(reservations=[reservation_payante]) == {
        "reservations": [Reservation.UNPAID],
        "billets": [Ticket.NOT_ACTIV, Ticket.NOT_ACTIV],
    }
    assert statuts_des_lignes_de_la_reservation(reservation_payante) == [
        LigneArticle.UNPAID
    ]

    # Billet à 0 € : aucune nouvelle session Stripe, validation gratuite.
    # / 0 € ticket: no new Stripe session, free validation.
    reserver_des_billets_sans_panier(
        client, acheteur, concert_a_zero_euro.evenement, {concert_a_zero_euro.tarif: 1}
    )
    reservation_a_zero_euro = Reservation.objects.get(
        user_commande=acheteur, event=concert_a_zero_euro.evenement
    )
    assert lieu.stripe.mock_create.call_count == 1
    assert etat_metier(reservations=[reservation_a_zero_euro]) == {
        "reservations": [Reservation.FREERES_USERACTIV],
        "billets": [Ticket.NOT_SCANNED],
    }
    assert statuts_des_lignes_de_la_reservation(reservation_a_zero_euro) == [
        LigneArticle.VALID
    ]

    # Ressource payante : une nouvelle session Stripe.
    # / Paid resource: one new Stripe session.
    reserver_une_ressource_sans_panier(client, location_payante)
    booking_payant = Booking.objects.get(
        user=acheteur, resource=location_payante.ressource
    )
    assert lieu.stripe.mock_create.call_count == 2
    assert etat_metier(booking=booking_payant) == {"booking": Booking.WAITING_PAYMENT}
    assert statuts_des_lignes_du_booking(booking_payant) == [LigneArticle.UNPAID]

    # Ressource à 0 € : aucune nouvelle session Stripe, validation gratuite.
    # / 0 € resource: no new Stripe session, free validation.
    reserver_une_ressource_sans_panier(client, location_a_zero_euro)
    booking_a_zero_euro = Booking.objects.get(
        user=acheteur, resource=location_a_zero_euro.ressource
    )
    assert lieu.stripe.mock_create.call_count == 2
    assert etat_metier(booking=booking_a_zero_euro) == {
        "booking": Booking.FREERES_USERACTIV
    }
    assert statuts_des_lignes_du_booking(booking_a_zero_euro) == [LigneArticle.VALID]
