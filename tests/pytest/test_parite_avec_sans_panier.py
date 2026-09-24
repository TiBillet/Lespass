"""
Parité : chaque achat doit donner le même résultat, avec et sans panier.
/ Parity: every purchase must give the same result, with and without the cart.

LOCALISATION : tests/pytest/test_parite_avec_sans_panier.py

Deux chaînes de code distinctes vendent la même chose :
- SANS panier (parcours direct, bouton « Payer maintenant ») : `EventMVT.reservation`
  (ReservationValidator + TicketCreator), `MembershipMVT.create` (MembershipValidator),
  `BookingViewSet.book` (validate_new_booking) ;
- AVEC panier : `/panier/add/…` puis `/panier/checkout/` (CommandeService.materialiser).
/ Two distinct code chains sell the same things: the direct flow and the cart.

Chaque test est paramétré par `parcours` et joue le VRAI formulaire du front avec le client
de test Django, puis la VRAIE vue de retour de paiement du parcours (session Stripe simulée
par `mock_stripe`), et vérifie le même état final des deux côtés.
/ Each test runs the real front form, then the real payment return view, for both flows.

PÉRIMÈTRE : l'acheteur est connecté, puisque le panier l'exige. Le parcours direct d'un
visiteur ANONYME n'est couvert que par le cas du billet à 0 € ; les autres parcours anonymes
relèvent des tests existants (tests/e2e/test_reservation_*.py, test_membership_*.py).
/ SCOPE: logged-in buyer (the cart requires it); anonymous direct flow only for the 0 € case.

Un cas marqué `xfail(strict=True)` prouve un défaut connu, noté dans
TECH_DOC/SESSIONS/PANIER/SPEC.md (§1 et §10, référence Cxx) et non corrigé dans ce chantier. Le test
échoue aujourd'hui ; le jour où le défaut est corrigé, il passe, et `strict` fait alors
échouer la suite pour qu'on retire la marque.
/ An `xfail(strict=True)` case proves a known, documented, unfixed defect.

Lancer / Run : make test ARGS="tests/pytest/test_parite_avec_sans_panier.py"
"""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from django_tenants.utils import tenant_context

from fabriques_panier import (
    ajouter_un_tarif,
    catalogue_stripe_simule,
    client_connecte,
    configuration_modifiee,
    creer_adhesion,
    creer_evenement_avec_tarif,
    creer_ressource_avec_tarif,
    creer_un_billet_deja_vendu,
    creer_une_adhesion_active,
    creer_utilisateur,
    identifiant_unique,
    noms_des_taches,
    taches_celery_enregistrees,
)

pytestmark = pytest.mark.django_db

SANS_PANIER = "sans_panier"
AVEC_PANIER = "avec_panier"
LES_DEUX_PARCOURS = [SANS_PANIER, AVEC_PANIER]

# Les formulaires du front sont envoyés par HTMX (hx-post) : on envoie le même en-tête que
# le navigateur. Sans lui, certaines vues prennent une branche que le front n'utilise jamais.
# / Front forms are sent by HTMX: send the same header as the browser.
EN_TETE_HTMX = {"HTTP_HX_REQUEST": "true"}


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
# Actions d'achat : le même geste, par l'un ou l'autre parcours
# / Purchase actions: the same gesture, through either flow
# --------------------------------------------------------------------------


def reserver_des_billets(
    parcours,
    client,
    acheteur,
    evenement,
    quantites_par_tarif,
    montants_libres=None,
    code_promo=None,
):
    """
    Réserve des billets par le formulaire de l'événement.
    / Books tickets through the event form.

    `quantites_par_tarif` : {tarif: quantité}. `montants_libres` : {tarif: "12.00"}.
    Sans panier : `POST /event/<slug>/reservation/`. Avec panier : ajout puis paiement.
    """
    donnees_du_formulaire = {"event": str(evenement.uuid)}
    for tarif, quantite in quantites_par_tarif.items():
        donnees_du_formulaire[str(tarif.uuid)] = str(quantite)
    for tarif, montant in (montants_libres or {}).items():
        donnees_du_formulaire[f"custom_amount_{tarif.uuid}"] = montant
    if code_promo:
        donnees_du_formulaire["promotional_code"] = code_promo

    if parcours == SANS_PANIER:
        donnees_du_formulaire["email"] = acheteur.email
        return client.post(
            f"/event/{evenement.slug}/reservation/",
            donnees_du_formulaire,
            **EN_TETE_HTMX,
        )

    reponse_de_l_ajout = client.post(
        "/panier/add/tickets_batch/", donnees_du_formulaire, **EN_TETE_HTMX
    )
    client.post("/panier/checkout/", **EN_TETE_HTMX)
    return reponse_de_l_ajout


def adherer(parcours, client, acheteur, tarif, montant_libre=None, newsletter=False):
    """
    Prend une adhésion par le formulaire d'adhésion.
    / Takes a membership through the membership form.

    Sans panier : `POST /memberships/`. Avec panier : ajout puis paiement.
    """
    donnees_du_formulaire = {
        "price": str(tarif.uuid),
        "firstname": "Ada",
        "lastname": "Lovelace",
    }
    if montant_libre is not None:
        donnees_du_formulaire[f"custom_amount_{tarif.uuid}"] = montant_libre
    if newsletter:
        donnees_du_formulaire["newsletter"] = "on"

    if parcours == SANS_PANIER:
        donnees_du_formulaire["email"] = acheteur.email
        donnees_du_formulaire["acknowledge"] = "true"
        if not newsletter:
            donnees_du_formulaire["newsletter"] = "false"
        return client.post("/memberships/", donnees_du_formulaire, **EN_TETE_HTMX)

    reponse_de_l_ajout = client.post(
        "/panier/add/membership/", donnees_du_formulaire, **EN_TETE_HTMX
    )
    client.post("/panier/checkout/", **EN_TETE_HTMX)
    return reponse_de_l_ajout


def reserver_une_ressource(
    parcours, client, location, tarif=None, nombre_d_heures=1, montant_libre=None
):
    """
    Réserve un créneau de ressource par le formulaire de réservation.
    / Books a resource slot through the booking form.

    Le formulaire envoie des dates sans fuseau, lues dans le fuseau courant.
    `montant_libre` : montant par heure saisi pour un tarif à prix libre ("12.00").
    Sans panier : `POST /booking/<ressource>/book/`. Avec panier : ajout puis paiement.
    """
    if tarif is None:
        tarif = location.tarif
    debut = location.debut_du_creneau
    fin = debut + timedelta(hours=nombre_d_heures)
    donnees_du_formulaire = {
        "resource": str(location.ressource.pk),
        "price_uuid": str(tarif.uuid),
        "start_datetime": debut.replace(tzinfo=None).isoformat(),
        "end_time": fin.replace(tzinfo=None).isoformat(),
        "firstname": "Ada",
        "lastname": "Lovelace",
    }
    if montant_libre is not None:
        donnees_du_formulaire[f"custom_amount_{tarif.uuid}"] = montant_libre

    if parcours == SANS_PANIER:
        return client.post(
            f"/booking/{location.ressource.pk}/book/",
            donnees_du_formulaire,
            **EN_TETE_HTMX,
        )

    reponse_de_l_ajout = client.post(
        "/panier/add/resource/", donnees_du_formulaire, **EN_TETE_HTMX
    )
    client.post("/panier/checkout/", **EN_TETE_HTMX)
    return reponse_de_l_ajout


def niveau_du_toast(reponse):
    """Le niveau du toast envoyé par `HX-Trigger` ('success', 'error'…), ou None.
    / The level of the toast sent through `HX-Trigger`, or None."""
    import json

    en_tete = reponse.get("HX-Trigger")
    if not en_tete:
        return None
    return json.loads(en_tete)["panierToast"]["level"]


def verifier_un_refus_propre(parcours, reponse):
    """
    Le refus vient de la validation, pas d'une panne ni d'un refus d'accès.
    Sans panier : la vue répond 200 (redirection HTMX avec message) ou 422 (formulaire
    réaffiché). Avec panier : l'AJOUT répond par un toast d'erreur.
    / The refusal comes from validation, not a crash nor an access denial.
    """
    assert reponse.status_code in (200, 422), (
        f"Réponse inattendue : {reponse.status_code}"
    )
    if parcours == AVEC_PANIER:
        assert niveau_du_toast(reponse) == "error"


# --------------------------------------------------------------------------
# Lecture du résultat et retour de paiement
# / Reading the result and payment return
# --------------------------------------------------------------------------


def paiement_des_lignes(**filtre_des_lignes):
    """
    Le paiement Stripe qui porte les lignes de vente filtrées. Les lignes pointent vers leur
    réservation, adhésion ou booking dans les deux parcours : c'est le chemin commun.
    / The Stripe payment carrying the filtered sale lines (common path for both flows).
    """
    from BaseBillet.models import Paiement_stripe

    filtre_des_paiements = {}
    for nom_du_filtre, valeur in filtre_des_lignes.items():
        filtre_des_paiements[f"lignearticles__{nom_du_filtre}"] = valeur
    return Paiement_stripe.objects.filter(**filtre_des_paiements).distinct().get()


def revenir_de_stripe(client, paiement, adhesion_directe=False):
    """
    Joue le retour navigateur depuis Stripe. L'adhésion directe revient sur
    `/memberships/<paiement>/stripe_return/` ; tout le reste sur `/event/<paiement>/stripe_return/`.
    / Plays the browser return from Stripe, on the return view of the flow.
    """
    if adhesion_directe:
        return client.get(f"/memberships/{paiement.uuid}/stripe_return/")
    return client.get(f"/event/{paiement.uuid}/stripe_return/")


def reservation_de(acheteur, evenement):
    """La réservation de l'acheteur pour cet événement, ou None.
    / The buyer's reservation for this event, or None."""
    from BaseBillet.models import Reservation

    return Reservation.objects.filter(user_commande=acheteur, event=evenement).first()


# --------------------------------------------------------------------------
# P1 à P7 — Billetterie
# / P1 to P7 — Ticketing
# --------------------------------------------------------------------------


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p1_billet_payant(lieu, parcours):
    """Billet payant : après le retour de Stripe, paiement validé, réservation payée, billets
    actifs, ligne validée au bon montant.
    / Paid ticket: after the Stripe return, everything is paid and active."""
    from BaseBillet.models import LigneArticle, Paiement_stripe, Reservation, Ticket

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")

    reserver_des_billets(
        parcours, client, acheteur, concert.evenement, {concert.tarif: 2}
    )
    reservation = reservation_de(acheteur, concert.evenement)
    paiement = paiement_des_lignes(reservation=reservation)
    revenir_de_stripe(client, paiement)

    paiement.refresh_from_db()
    reservation.refresh_from_db()
    assert paiement.status == Paiement_stripe.VALID
    assert reservation.status == Reservation.PAID
    assert reservation.tickets.count() == 2
    for billet in reservation.tickets.all():
        assert billet.status == Ticket.NOT_SCANNED
    ligne = LigneArticle.objects.get(reservation=reservation)
    assert ligne.status == LigneArticle.VALID
    assert ligne.amount == 1000
    assert ligne.qty == 2


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p2_billet_gratuit_freeres(lieu, parcours):
    """Réservation gratuite (`FREERES`) : confirmée tout de suite, billets actifs, aucune
    ligne de vente, aucun appel Stripe, billets envoyés une seule fois.
    / Free reservation: confirmed at once, active tickets, no sale line, no Stripe, one mail."""
    from BaseBillet.models import LigneArticle, Product, Reservation, Ticket

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    atelier = creer_evenement_avec_tarif(categorie=Product.FREERES)

    reserver_des_billets(
        parcours, client, acheteur, atelier.evenement, {atelier.tarif: 1}
    )

    reservation = reservation_de(acheteur, atelier.evenement)
    assert reservation.status == Reservation.FREERES_USERACTIV
    assert reservation.tickets.get().status == Ticket.NOT_SCANNED
    assert not LigneArticle.objects.filter(reservation=reservation).exists()
    assert not lieu.stripe.mock_create.called
    assert noms_des_taches(lieu.taches_demandees).count("ticket_celery_mailer") == 1


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p2bis_billet_payant_a_zero_euro_est_gratuit(
    lieu, parcours, django_capture_on_commit_callbacks
):
    """
    Billet de catégorie « payant » (`BILLET`) à 0 € : gratuit dans les deux parcours (décision
    du mainteneur, C21). Pas de paiement Stripe ; réservation confirmée, billets actifs, ligne
    validée en « offert ».
    / A paid-category ticket at 0 € is free in both flows: no Stripe checkout.
    """
    from BaseBillet.models import LigneArticle, PaymentMethod, Reservation, Ticket

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="0.00")

    # L'envoi à LaBoutik part après la validation en base : on exécute ces rappels.
    # / The LaBoutik sale is sent after the commit: run those callbacks.
    with django_capture_on_commit_callbacks(execute=True):
        reserver_des_billets(
            parcours, client, acheteur, concert.evenement, {concert.tarif: 1}
        )

    reservation = reservation_de(acheteur, concert.evenement)
    assert not lieu.stripe.mock_create.called
    assert reservation.status == Reservation.FREERES_USERACTIV
    assert reservation.tickets.get().status == Ticket.NOT_SCANNED
    ligne = LigneArticle.objects.get(reservation=reservation)
    assert ligne.status == LigneArticle.VALID
    assert ligne.payment_method == PaymentMethod.FREE
    taches_demandees = noms_des_taches(lieu.taches_demandees)
    assert taches_demandees.count("ticket_celery_mailer") == 1
    # La vente à 0 € est envoyée à LaBoutik comme les autres (ligne passée par « payée »).
    # / The 0 € sale is sent to LaBoutik like any other (line went through "paid").
    assert taches_demandees.count("send_sale_to_laboutik") == 1


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p3_billet_prix_libre_facture_le_montant_saisi(lieu, parcours):
    """Prix libre (minimum 5 €) : la ligne porte le montant saisi, 12 €.
    / Free price (minimum 5 €): the line carries the typed amount, 12 €."""
    from BaseBillet.models import LigneArticle

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="5.00", prix_libre=True)

    reserver_des_billets(
        parcours,
        client,
        acheteur,
        concert.evenement,
        {concert.tarif: 1},
        montants_libres={concert.tarif: "12.00"},
    )

    reservation = reservation_de(acheteur, concert.evenement)
    assert LigneArticle.objects.get(reservation=reservation).amount == 1200


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p3_billet_prix_libre_sous_le_minimum_est_refuse(lieu, parcours):
    """Prix libre saisi sous le minimum : aucune réservation.
    / Free price below the minimum: no reservation."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="5.00", prix_libre=True)

    reponse = reserver_des_billets(
        parcours,
        client,
        acheteur,
        concert.evenement,
        {concert.tarif: 1},
        montants_libres={concert.tarif: "2.00"},
    )

    verifier_un_refus_propre(parcours, reponse)
    assert reservation_de(acheteur, concert.evenement) is None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p3_billet_prix_libre_negatif_est_refuse(lieu, parcours):
    """Prix libre dont le minimum est 0 €, montant saisi -20 € : refusé, aucune réservation.
    Un montant négatif rendrait la commande gratuite (total ≤ 0) et enverrait les billets.
    / Free price with a 0 € minimum, -20 € typed: refused, no reservation. A negative amount
    would make the whole order free and send the tickets."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="0.00", prix_libre=True)

    reponse = reserver_des_billets(
        parcours,
        client,
        acheteur,
        concert.evenement,
        {concert.tarif: 1},
        montants_libres={concert.tarif: "-20.00"},
    )

    verifier_un_refus_propre(parcours, reponse)
    assert reservation_de(acheteur, concert.evenement) is None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p10_adhesion_prix_libre_a_zero_sous_le_minimum_est_refusee(lieu, parcours):
    """Adhésion à prix libre dont le minimum vaut 10 €, montant saisi 0 : refusée. Le 0 ne doit
    pas être remplacé en silence par le minimum, sinon la personne est débitée de 10 € sans
    l'avoir demandé.
    / Free-price membership with a 10 € minimum, 0 typed: refused. The 0 must not be silently
    replaced by the minimum, which would charge 10 € nobody asked for."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="10.00", prix_libre=True)

    adherer(parcours, client, acheteur, adhesion.tarif, montant_libre="0")

    assert adhesion_de(acheteur, adhesion) is None
    assert not lieu.stripe.mock_create.called


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p10_adhesion_prix_libre_negative_est_refusee(lieu, parcours):
    """Adhésion à prix libre dont le minimum est 0 €, montant saisi -20 € : refusée, aucune
    adhésion créée.
    / Free-price membership with a 0 € minimum, -20 € typed: refused, no membership."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="0.00", prix_libre=True)

    adherer(parcours, client, acheteur, adhesion.tarif, montant_libre="-20.00")

    assert adhesion_de(acheteur, adhesion) is None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p3_billet_prix_libre_sous_le_minimum_stripe_est_refuse(lieu, parcours):
    """Prix libre à 0,30 € (sous le minimum Stripe de 0,50 €) : refusé avant le paiement.
    / Free price at 0.30 € (below Stripe's 0.50 € minimum): refused before payment."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="0.00", prix_libre=True)

    reserver_des_billets(
        parcours,
        client,
        acheteur,
        concert.evenement,
        {concert.tarif: 1},
        montants_libres={concert.tarif: "0.30"},
    )

    assert reservation_de(acheteur, concert.evenement) is None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p4_code_promo_ne_remise_que_son_produit(lieu, parcours):
    """Événement à deux produits billet, code -50 % sur le produit A : seul A est remisé.
    / Two ticket products, -50 % code on product A: only A is discounted."""
    from BaseBillet.models import LigneArticle, Product, PromotionalCode

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")
    produit_b = Product.objects.create(
        name=f"TEST_panier billet B {identifiant_unique()}",
        categorie_article=Product.BILLET,
    )
    concert.evenement.products.add(produit_b)
    tarif_b = ajouter_un_tarif(produit_b, prix="10.00", nom="Plein tarif B")
    code_promo = PromotionalCode.objects.create(
        name=f"TEST_panier_moitie_{identifiant_unique()}",
        discount_rate=Decimal("50.00"),
        product=concert.produit,
    )

    reserver_des_billets(
        parcours,
        client,
        acheteur,
        concert.evenement,
        {concert.tarif: 1, tarif_b: 1},
        code_promo=code_promo.name,
    )

    reservation = reservation_de(acheteur, concert.evenement)
    ligne_a = LigneArticle.objects.get(
        reservation=reservation, pricesold__price=concert.tarif
    )
    ligne_b = LigneArticle.objects.get(
        reservation=reservation, pricesold__price=tarif_b
    )
    assert ligne_a.amount == 500
    assert ligne_b.amount == 1000
    # Un seul paiement Stripe pour toute la réservation (ou toute la Commande).
    # / One Stripe payment for the whole reservation (or the whole order).
    assert lieu.stripe.mock_create.call_count == 1


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p4_code_promo_d_un_produit_non_choisi_est_refuse(lieu, parcours):
    """Code promo lié à un autre produit que ceux choisis : la demande est refusée (sinon le
    billet partirait au plein tarif sans que l'acheteur le sache), rien n'est réservé.
    / Promo code linked to a product that was not chosen: refused, nothing is booked."""
    from BaseBillet.models import Product, PromotionalCode

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")
    produit_non_choisi = Product.objects.create(
        name=f"TEST_panier billet B {identifiant_unique()}",
        categorie_article=Product.BILLET,
    )
    concert.evenement.products.add(produit_non_choisi)
    ajouter_un_tarif(produit_non_choisi, prix="10.00", nom="Plein tarif B")
    code_promo = PromotionalCode.objects.create(
        name=f"TEST_panier_moitie_{identifiant_unique()}",
        discount_rate=Decimal("50.00"),
        product=produit_non_choisi,
    )

    reponse = reserver_des_billets(
        parcours,
        client,
        acheteur,
        concert.evenement,
        {concert.tarif: 1},
        code_promo=code_promo.name,
    )

    verifier_un_refus_propre(parcours, reponse)
    assert reservation_de(acheteur, concert.evenement) is None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize(
    "quantite_trafiquee", ["Infinity", "1e1000000", "-1e1000000", "10000"]
)
def test_une_quantite_demesuree_est_refusee_sans_bloquer_le_serveur(
    lieu, parcours, quantite_trafiquee
):
    """Quantité infinie ou démesurée (formulaire trafiqué, possible sans compte en direct) :
    refus propre, réponse immédiate, rien de réservé. Convertir « 1e1000000 » en entier
    bloquerait le serveur plusieurs secondes.
    / Infinite or huge quantity: clean refusal, immediate answer, nothing booked."""
    import time

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00", jauge_max=30000)

    debut = time.monotonic()
    reponse = reserver_des_billets(
        parcours,
        client,
        acheteur,
        concert.evenement,
        {concert.tarif: quantite_trafiquee},
    )
    duree_en_secondes = time.monotonic() - debut

    verifier_un_refus_propre(parcours, reponse)
    assert reservation_de(acheteur, concert.evenement) is None
    # Sans la garde, int(Decimal("1e1000000")) prend environ 17 s (mesure du 2026-09-24).
    # Avec elle, la reponse arrive en moins d'1 s. Le seuil de 5 s separe nettement les
    # deux cas, sans echouer quand la machine est chargee pendant la suite complete
    # (le chronometre couvre l'ajout ET le paiement cote panier).
    # / Without the guard, the conversion takes ~17 s; with it, under 1 s. 5 s separates
    #   both cases without failing under load during the full suite.
    assert duree_en_secondes < 5


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize(
    "etat_de_l_evenement",
    ["termine", "commence_depuis_2_jours_sans_date_de_fin", "archive"],
)
def test_un_evenement_qui_n_est_plus_en_vente_est_refuse(
    lieu, parcours, etat_de_l_evenement
):
    """Événement terminé, non publié ou archivé (formulaire envoyé quand même) : refusé,
    rien n'est réservé.
    / Ended, unpublished or archived event: refused, nothing is booked."""
    from test_panier_session import mettre_l_evenement_dans_l_etat

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")
    mettre_l_evenement_dans_l_etat(concert, etat_de_l_evenement)

    reponse = reserver_des_billets(
        parcours, client, acheteur, concert.evenement, {concert.tarif: 1}
    )

    verifier_un_refus_propre(parcours, reponse)
    assert reservation_de(acheteur, concert.evenement) is None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize(
    "etat_de_l_evenement",
    ["en_cours_jusqu_a_demain", "commence_depuis_2_h_sans_date_de_fin", "non_publie"],
)
def test_un_evenement_commence_mais_pas_termine_reste_en_vente(
    lieu, parcours, etat_de_l_evenement
):
    """Festival commencé il y a 3 jours et fini demain, événement sans date de fin commencé
    il y a 2 h, ou événement non publié (lien direct) : la réservation est créée.
    / Ongoing festival, event without end started 2 h ago, or unpublished event: booked."""
    from test_panier_session import mettre_l_evenement_dans_l_etat

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")
    mettre_l_evenement_dans_l_etat(concert, etat_de_l_evenement)

    with configuration_modifiee(allow_concurrent_bookings=True):
        reserver_des_billets(
            parcours, client, acheteur, concert.evenement, {concert.tarif: 1}
        )

    assert reservation_de(acheteur, concert.evenement) is not None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p4_code_promo_inconnu_est_refuse(lieu, parcours):
    """Un code promo qui n'existe pas : la demande est refusée, rien n'est réservé.
    / An unknown promo code: the request is refused, nothing is booked."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")

    reponse = reserver_des_billets(
        parcours,
        client,
        acheteur,
        concert.evenement,
        {concert.tarif: 1},
        code_promo="TEST_panier_CODE_QUI_N_EXISTE_PAS",
    )

    verifier_un_refus_propre(parcours, reponse)
    assert reservation_de(acheteur, concert.evenement) is None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p5_tarif_adherent_refuse_sans_adhesion(lieu, parcours):
    """Tarif réservé aux adhérents, acheteur sans adhésion : aucune réservation.
    / Members-only price, buyer without membership: no reservation."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="5.00")
    adhesion = creer_adhesion(prix="15.00")
    concert.tarif.adhesions_obligatoires.add(adhesion.produit)

    reponse = reserver_des_billets(
        parcours, client, acheteur, concert.evenement, {concert.tarif: 1}
    )

    verifier_un_refus_propre(parcours, reponse)
    assert reservation_de(acheteur, concert.evenement) is None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p5_tarif_adherent_accepte_avec_une_adhesion_active(lieu, parcours):
    """Tarif réservé aux adhérents, adhésion active en base : réservation créée.
    / Members-only price, active membership in the DB: reservation created."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="5.00")
    adhesion = creer_adhesion(prix="15.00")
    concert.tarif.adhesions_obligatoires.add(adhesion.produit)
    creer_une_adhesion_active(acheteur, adhesion, jours_restants=30)

    reserver_des_billets(
        parcours, client, acheteur, concert.evenement, {concert.tarif: 1}
    )

    assert reservation_de(acheteur, concert.evenement) is not None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p5_tarif_adherent_refuse_avec_une_adhesion_expiree(lieu, parcours):
    """Tarif réservé aux adhérents, adhésion expirée : aucune réservation.
    / Members-only price, expired membership: no reservation."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="5.00")
    adhesion = creer_adhesion(prix="15.00")
    concert.tarif.adhesions_obligatoires.add(adhesion.produit)
    creer_une_adhesion_active(acheteur, adhesion, jours_restants=-1)

    reponse = reserver_des_billets(
        parcours, client, acheteur, concert.evenement, {concert.tarif: 1}
    )

    verifier_un_refus_propre(parcours, reponse)
    assert reservation_de(acheteur, concert.evenement) is None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p6_limite_par_personne_de_l_evenement_depassee_dans_la_demande(lieu, parcours):
    """Maximum 2 billets par personne, demande de 3 : refusé.
    / Maximum 2 tickets per person, request for 3: refused."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00", max_par_personne_evenement=2)

    reponse = reserver_des_billets(
        parcours, client, acheteur, concert.evenement, {concert.tarif: 3}
    )

    verifier_un_refus_propre(parcours, reponse)
    assert reservation_de(acheteur, concert.evenement) is None


PARAMETRE_DE_LA_LIMITE_PAR_NIVEAU = {
    "evenement": "max_par_personne_evenement",
    "produit": "max_par_personne_produit",
    "tarif": "max_par_personne_tarif",
}


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize("niveau_de_la_limite", ["evenement", "produit", "tarif"])
def test_p6_limite_par_personne_compte_les_billets_deja_achetes(
    lieu, parcours, niveau_de_la_limite
):
    """Maximum 2 par personne (événement, produit ou tarif), 1 billet déjà acheté, demande
    de 2 : refusé (1 + 2 > 2).
    / Maximum 2 per person (event, product or price), 1 already bought, request 2: refused."""
    from BaseBillet.models import Reservation

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    limite = {PARAMETRE_DE_LA_LIMITE_PAR_NIVEAU[niveau_de_la_limite]: 2}
    concert = creer_evenement_avec_tarif(prix="10.00", **limite)
    creer_un_billet_deja_vendu(acheteur, concert)

    # Réservations simultanées autorisées : le seul motif de refus possible est la limite.
    # / Concurrent bookings allowed: the per-person limit is the only possible refusal.
    with configuration_modifiee(allow_concurrent_bookings=True):
        reserver_des_billets(
            parcours, client, acheteur, concert.evenement, {concert.tarif: 2}
        )

    nouvelles_reservations = Reservation.objects.filter(
        user_commande=acheteur, event=concert.evenement
    ).exclude(status=Reservation.VALID)
    assert not nouvelles_reservations.exists()


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize("niveau_de_la_limite", ["evenement", "produit", "tarif"])
def test_p6_limite_par_personne_accepte_ce_qui_reste(
    lieu, parcours, niveau_de_la_limite
):
    """Maximum 2 par personne, 1 billet déjà acheté, demande de 1 : accepté (1 + 1 = 2).
    / Maximum 2 per person, 1 already bought, request 1: accepted."""
    from BaseBillet.models import Reservation

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    limite = {PARAMETRE_DE_LA_LIMITE_PAR_NIVEAU[niveau_de_la_limite]: 2}
    concert = creer_evenement_avec_tarif(prix="10.00", **limite)
    creer_un_billet_deja_vendu(acheteur, concert)

    with configuration_modifiee(allow_concurrent_bookings=True):
        reserver_des_billets(
            parcours, client, acheteur, concert.evenement, {concert.tarif: 1}
        )

    nouvelles_reservations = Reservation.objects.filter(
        user_commande=acheteur, event=concert.evenement
    ).exclude(status=Reservation.VALID)
    assert nouvelles_reservations.exists()


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p7_tarif_epuise_est_refuse(lieu, parcours):
    """Stock du tarif : 1, déjà vendu. Nouvelle demande : refusée.
    / Price stock 1, already sold. New request: refused."""
    from BaseBillet.models import Reservation

    acheteur = creer_utilisateur()
    autre_acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00", stock_du_tarif=1)
    creer_un_billet_deja_vendu(autre_acheteur, concert)

    reponse = reserver_des_billets(
        parcours, client, acheteur, concert.evenement, {concert.tarif: 1}
    )

    verifier_un_refus_propre(parcours, reponse)
    assert not Reservation.objects.filter(user_commande=acheteur).exists()


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p7_quantite_demandee_superieure_au_stock_restant_est_refusee(lieu, parcours):
    """Stock du tarif : 2, dont 1 vendu. Demande de 2 : refusée (il n'en reste qu'un).
    / Price stock 2, 1 sold. Request for 2: refused (only one left)."""
    acheteur = creer_utilisateur()
    autre_acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00", stock_du_tarif=2)
    creer_un_billet_deja_vendu(autre_acheteur, concert)

    reserver_des_billets(
        parcours, client, acheteur, concert.evenement, {concert.tarif: 2}
    )

    assert reservation_de(acheteur, concert.evenement) is None


# --------------------------------------------------------------------------
# P8 à P14 — Adhésions
# / P8 to P14 — Memberships
# --------------------------------------------------------------------------


def adhesion_de(acheteur, adhesion):
    """La dernière adhésion de l'acheteur à ce produit.
    / The buyer's latest membership to this product."""
    from BaseBillet.models import Membership

    return Membership.objects.filter(
        user=acheteur, price__product=adhesion.produit
    ).last()


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p8_adhesion_payante(lieu, parcours):
    """Adhésion payante : après le retour de Stripe, adhésion active avec échéance, ligne
    validée, paiement validé, mail demandé, adhérent rattaché au lieu.
    / Paid membership: active with a deadline, line and payment valid, mail requested."""
    from BaseBillet.models import LigneArticle, Membership, Paiement_stripe

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="15.00")

    adherer(parcours, client, acheteur, adhesion.tarif)
    adhesion_creee = adhesion_de(acheteur, adhesion)
    paiement = paiement_des_lignes(membership=adhesion_creee)
    revenir_de_stripe(client, paiement, adhesion_directe=(parcours == SANS_PANIER))

    adhesion_creee.refresh_from_db()
    paiement.refresh_from_db()
    assert paiement.status == Paiement_stripe.VALID
    assert adhesion_creee.status == Membership.ONCE
    assert adhesion_creee.deadline is not None
    assert adhesion_creee.contribution_value == Decimal("15.00")
    assert (
        LigneArticle.objects.get(membership=adhesion_creee).status == LigneArticle.VALID
    )
    assert "send_membership_invoice_to_email" in noms_des_taches(lieu.taches_demandees)
    assert acheteur.client_achat.filter(pk=lieu.tenant.pk).exists()


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p9_adhesion_gratuite(lieu, parcours):
    """Adhésion à 0 € : active tout de suite, sans Stripe, mail demandé, adhérent rattaché.
    / Free membership: active at once, no Stripe, mail requested, member linked to the venue."""
    from BaseBillet.models import LigneArticle, Membership, PaymentMethod

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="0.00")

    adherer(parcours, client, acheteur, adhesion.tarif)

    adhesion_creee = adhesion_de(acheteur, adhesion)
    assert not lieu.stripe.mock_create.called
    assert adhesion_creee.status == Membership.ONCE
    assert adhesion_creee.deadline is not None
    ligne = LigneArticle.objects.get(membership=adhesion_creee)
    assert ligne.status == LigneArticle.VALID
    assert ligne.payment_method == PaymentMethod.FREE
    assert "send_membership_invoice_to_email" in noms_des_taches(lieu.taches_demandees)
    assert acheteur.client_achat.filter(pk=lieu.tenant.pk).exists()


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p10_adhesion_prix_libre(lieu, parcours):
    """Adhésion à prix libre : la contribution et la ligne portent le montant saisi, 25 €.
    / Free-price membership: contribution and line carry the typed amount, 25 €."""
    from BaseBillet.models import LigneArticle

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="10.00", prix_libre=True)

    adherer(parcours, client, acheteur, adhesion.tarif, montant_libre="25.00")

    adhesion_creee = adhesion_de(acheteur, adhesion)
    assert adhesion_creee.contribution_value == Decimal("25.00")
    assert LigneArticle.objects.get(membership=adhesion_creee).amount == 2500


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p10_adhesion_prix_libre_sous_le_minimum_stripe_est_refusee(lieu, parcours):
    """Adhésion à prix libre (minimum 0 €) à 0,30 €, sous le minimum Stripe de 0,50 € :
    refusée avant le paiement, aucune adhésion créée.
    / Free-price membership at 0.30 € (below Stripe's 0.50 € minimum): refused before
    payment, no membership created."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="0.00", prix_libre=True)

    adherer(parcours, client, acheteur, adhesion.tarif, montant_libre="0.30")

    assert adhesion_de(acheteur, adhesion) is None
    assert not lieu.stripe.mock_create.called


def creer_une_monnaie_de_recompense(tenant):
    """Une monnaie Fedow publique, pour la récompense d'adhésion.
    / A public Fedow asset, for the membership reward."""
    from AuthBillet.models import Wallet
    from fedow_public.models import AssetFedowPublic

    portefeuille = Wallet.objects.create(origin=tenant, name="TEST_panier portefeuille")
    return AssetFedowPublic.objects.create(
        name=f"TEST_panier monnaie {identifiant_unique()}",
        currency_code="TST",
        wallet_origin=portefeuille,
        origin=tenant,
    )


def executer_la_recompense(ligne):
    """
    Exécute la vraie tâche de récompense pour cette ligne, avec Fedow simulé.
    Rend le faux appel de versement, pour lire le montant et la monnaie envoyés.
    / Runs the real reward task for this line with Fedow faked; returns the fake transfer call.
    """
    from BaseBillet.tasks import refill_from_lespass_to_user_wallet_from_price_solded

    configuration_fedow = MagicMock()
    configuration_fedow.can_fedow.return_value = True
    with (
        patch("BaseBillet.tasks.time.sleep"),
        patch("BaseBillet.tasks.FedowAPI") as fedow_api_simule,
        patch(
            "fedow_connect.models.FedowConfig.get_solo",
            return_value=configuration_fedow,
        ),
    ):
        refill_from_lespass_to_user_wallet_from_price_solded(ligne.pk)
    return fedow_api_simule.return_value.transaction.refill_from_lespass_to_user_wallet


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize("prix_de_l_adhesion", ["15.00", "0.00"])
def test_p11_adhesion_avec_recompense_monnaie(
    lieu, parcours, prix_de_l_adhesion, django_capture_on_commit_callbacks
):
    """
    Adhésion qui verse 5 jetons : la tâche de récompense est demandée pour la ligne, et
    l'exécuter verse 500 centimes de la bonne monnaie à l'adhérent. Payante et gratuite.
    / Membership rewarding 5 tokens: the reward task is requested for the line and, when run,
    sends 500 cents of the right asset to the member. Paid and free.
    """
    from BaseBillet.models import LigneArticle

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix=prix_de_l_adhesion)
    monnaie = creer_une_monnaie_de_recompense(lieu.tenant)
    adhesion.tarif.fedow_reward_enabled = True
    adhesion.tarif.fedow_reward_asset = monnaie
    adhesion.tarif.fedow_reward_amount = Decimal("5.00")
    adhesion.tarif.save()

    # La récompense part après la validation en base : on exécute ces rappels.
    # / The reward is sent after the commit: run those callbacks.
    with django_capture_on_commit_callbacks(execute=True):
        adherer(parcours, client, acheteur, adhesion.tarif)
        adhesion_creee = adhesion_de(acheteur, adhesion)
        if prix_de_l_adhesion != "0.00":
            paiement = paiement_des_lignes(membership=adhesion_creee)
            revenir_de_stripe(
                client, paiement, adhesion_directe=(parcours == SANS_PANIER)
            )

    ligne = LigneArticle.objects.get(membership=adhesion_creee)
    taches_de_recompense = []
    for nom_de_la_tache, arguments in lieu.taches_demandees:
        if nom_de_la_tache == "refill_from_lespass_to_user_wallet_from_price_solded":
            taches_de_recompense.append(arguments)
    assert taches_de_recompense == [(ligne.pk,)]

    versement = executer_la_recompense(ligne)

    assert versement.call_count == 1
    assert versement.call_args.kwargs["user"] == acheteur
    assert versement.call_args.kwargs["amount"] == 500
    assert versement.call_args.kwargs["asset"] == monnaie


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p12_adhesion_a_validation_manuelle(lieu, parcours):
    """
    Adhésion à validation manuelle : le direct la crée en attente de validation, sans
    paiement ; le panier la refuse proprement (toast d'erreur), sans rien créer.
    / Manual-validation membership: direct creates it waiting for validation, the cart refuses.
    """
    from BaseBillet.models import Membership

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="15.00", validation_manuelle=True)

    adherer(parcours, client, acheteur, adhesion.tarif)

    assert not lieu.stripe.mock_create.called
    if parcours == SANS_PANIER:
        assert adhesion_de(acheteur, adhesion).status == Membership.ADMIN_WAITING
    else:
        assert adhesion_de(acheteur, adhesion) is None
        assert client.session.get("panier", {}).get("items", []) == []


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p13_adhesion_recurrente(lieu, parcours):
    """
    Adhésion récurrente : le direct ouvre un paiement en mode abonnement ; le panier la
    refuse proprement, sans rien créer.
    / Recurring membership: direct opens a subscription checkout, the cart refuses.
    """
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="15.00", recurrente=True)

    adherer(parcours, client, acheteur, adhesion.tarif)

    if parcours == SANS_PANIER:
        assert lieu.stripe.mock_create.call_args.kwargs["mode"] == "subscription"
    else:
        assert not lieu.stripe.mock_create.called
        assert adhesion_de(acheteur, adhesion) is None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p14_prelevement_sepa_propose_pour_une_adhesion(lieu, parcours):
    """Adhésion seule : le prélèvement SEPA est proposé (si le lieu l'accepte).
    / Membership alone: SEPA debit is offered (when the venue accepts it)."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="15.00")

    with configuration_modifiee(stripe_accept_sepa=True):
        adherer(parcours, client, acheteur, adhesion.tarif)

    moyens_proposes = lieu.stripe.mock_create.call_args.kwargs["payment_method_types"]
    assert "sepa_debit" in moyens_proposes


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p14_prelevement_sepa_refuse_pour_un_billet(lieu, parcours):
    """Billet : pas de SEPA (le débit peut prendre des jours).
    / Ticket: no SEPA (the debit can take days)."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")

    with configuration_modifiee(stripe_accept_sepa=True):
        reserver_des_billets(
            parcours, client, acheteur, concert.evenement, {concert.tarif: 1}
        )

    moyens_proposes = lieu.stripe.mock_create.call_args.kwargs["payment_method_types"]
    assert moyens_proposes == ["card"]


# --------------------------------------------------------------------------
# P15 à P17 — Ressources
# / P15 to P17 — Resources
# --------------------------------------------------------------------------


def booking_de(acheteur, location):
    """Le booking de l'acheteur sur cette ressource, ou None.
    / The buyer's booking on this resource, or None."""
    from booking.models import Booking

    return Booking.objects.filter(user=acheteur, resource=location.ressource).first()


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p15_ressource_payante(lieu, parcours):
    """Ressource payante, 2 h à 12 € : après le retour de Stripe, booking payé, ligne validée
    à 24 €.
    / Paid resource, 2 hours at 12 €: after the Stripe return, booking paid, line valid at 24 €."""
    from BaseBillet.models import LigneArticle
    from booking.models import Booking

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="12.00")

    reserver_une_ressource(parcours, client, location, nombre_d_heures=2)
    booking = booking_de(acheteur, location)
    paiement = paiement_des_lignes(booking=booking)
    revenir_de_stripe(client, paiement)

    booking.refresh_from_db()
    assert booking.status == Booking.PAID_BY_USER
    ligne = LigneArticle.objects.get(booking=booking)
    assert ligne.status == LigneArticle.VALID
    assert ligne.amount == 2400


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p16_ressource_gratuite(lieu, parcours):
    """Ressource gratuite : booking confirmé sans Stripe, ligne validée en « offert ».
    / Free resource: booking confirmed without Stripe, line valid as "free"."""
    from BaseBillet.models import LigneArticle, PaymentMethod
    from booking.models import Booking

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="0.00")

    reserver_une_ressource(parcours, client, location)

    booking = booking_de(acheteur, location)
    assert not lieu.stripe.mock_create.called
    assert booking.status == Booking.FREERES_USERACTIV
    ligne = LigneArticle.objects.get(booking=booking)
    assert ligne.status == LigneArticle.VALID
    assert ligne.payment_method == PaymentMethod.FREE


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p17_ressource_a_tarif_adherent_refusee_sans_adhesion(lieu, parcours):
    """Tarif de ressource réservé aux adhérents, acheteur sans adhésion : aucun booking.
    / Members-only resource price, buyer without membership: no booking."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="3.00")
    adhesion = creer_adhesion(prix="15.00")
    location.tarif.adhesions_obligatoires.add(adhesion.produit)

    reponse = reserver_une_ressource(parcours, client, location)

    verifier_un_refus_propre(parcours, reponse)
    assert booking_de(acheteur, location) is None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p17_ressource_au_tarif_d_une_autre_ressource_est_refusee(lieu, parcours):
    """Tarif gratuit d'une autre ressource utilisé pour réserver celle-ci : aucun booking.
    / Another resource's free price used to book this one: no booking."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    salle_payante = creer_ressource_avec_tarif(prix="12.00")
    salle_gratuite = creer_ressource_avec_tarif(prix="0.00")

    reponse = reserver_une_ressource(
        parcours, client, salle_payante, tarif=salle_gratuite.tarif
    )

    verifier_un_refus_propre(parcours, reponse)
    assert booking_de(acheteur, salle_payante) is None


@pytest.mark.parametrize("retrait", ["tarif_depublie", "produit_archive"])
@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p17_ressource_a_tarif_retire_de_la_vente_est_refusee(lieu, parcours, retrait):
    """Tarif dépublié, ou produit de la ressource archivé : aucun booking.
    / Unpublished price, or archived resource product: no booking."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="12.00")
    if retrait == "tarif_depublie":
        location.tarif.publish = False
        location.tarif.save(update_fields=["publish"])
    else:
        location.produit.archive = True
        location.produit.save(update_fields=["archive"])

    reponse = reserver_une_ressource(parcours, client, location)

    verifier_un_refus_propre(parcours, reponse)
    assert booking_de(acheteur, location) is None


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p17_ressource_a_tarif_adherent_acceptee_avec_une_adhesion_active(
    lieu, parcours
):
    """Tarif de ressource réservé aux adhérents, acheteur avec une adhésion active : le booking
    est créé (en attente du paiement).
    / Members-only resource price, buyer with an active membership: the booking is created."""
    from booking.models import Booking

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="3.00")
    adhesion = creer_adhesion(prix="15.00")
    location.tarif.adhesions_obligatoires.add(adhesion.produit)
    creer_une_adhesion_active(acheteur, adhesion)

    reserver_une_ressource(parcours, client, location)

    booking = booking_de(acheteur, location)
    assert booking is not None
    assert booking.status == Booking.WAITING_PAYMENT


# --------------------------------------------------------------------------
# P18 à P20 — Retour, limites d'adhésion, formulaire
# / P18 to P20 — Return, membership limits, form
# --------------------------------------------------------------------------


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p18_revenir_deux_fois_de_stripe_ne_duplique_rien(lieu, parcours):
    """Retour puis rechargement de la page de retour : aucun billet ni mail en double.
    / Return then reload of the return page: no duplicate ticket or mail."""
    from BaseBillet.models import Ticket

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")
    reserver_des_billets(
        parcours, client, acheteur, concert.evenement, {concert.tarif: 2}
    )
    reservation = reservation_de(acheteur, concert.evenement)
    paiement = paiement_des_lignes(reservation=reservation)
    revenir_de_stripe(client, paiement)
    nombre_de_mails_apres_le_premier_retour = noms_des_taches(
        lieu.taches_demandees
    ).count("ticket_celery_mailer")

    revenir_de_stripe(client, paiement)

    assert Ticket.objects.filter(reservation=reservation).count() == 2
    nombre_de_mails_apres_le_second_retour = noms_des_taches(
        lieu.taches_demandees
    ).count("ticket_celery_mailer")
    assert (
        nombre_de_mails_apres_le_second_retour
        == nombre_de_mails_apres_le_premier_retour
    )


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p19_adhesion_limitee_a_une_par_personne(lieu, parcours):
    """Adhésion limitée à 1 par personne, déjà active : une deuxième est refusée.
    / Membership limited to 1 per person, already active: a second one is refused."""
    from BaseBillet.models import Membership

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="15.00", max_par_personne=1)
    creer_une_adhesion_active(acheteur, adhesion)

    adherer(parcours, client, acheteur, adhesion.tarif)

    assert Membership.objects.filter(user=acheteur, price=adhesion.tarif).count() == 1


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p19_adhesion_a_un_produit_limite_refusee_sur_un_autre_tarif(lieu, parcours):
    """Produit d'adhésion limité à 1 par personne, adhésion active au tarif plein : une
    adhésion au tarif réduit du même produit est refusée.
    / Membership product limited to 1 per person, active on the full price: the reduced
    price of the same product is refused."""
    from BaseBillet.models import Membership, Price, Product

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="15.00")
    # update() : pas de signal post_save du produit (il appellerait Fedow).
    # / update(): no Product post_save signal (it would call Fedow).
    Product.objects.filter(pk=adhesion.produit.pk).update(max_per_user=1)
    tarif_reduit = ajouter_un_tarif(
        adhesion.produit, prix="10.00", subscription_type=Price.YEAR
    )
    creer_une_adhesion_active(acheteur, adhesion)

    adherer(parcours, client, acheteur, tarif_reduit)

    assert (
        Membership.objects.filter(user=acheteur, price__product=adhesion.produit).count()
        == 1
    )


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p19_adhesion_au_stock_epuise_est_refusee(lieu, parcours):
    """Tarif d'adhésion au stock de 1, déjà pris par quelqu'un : refusé.
    / Membership price with a stock of 1, already taken: refused."""
    from BaseBillet.models import Membership

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="15.00")
    adhesion.tarif.stock = 1
    adhesion.tarif.save()
    creer_une_adhesion_active(creer_utilisateur(), adhesion)

    adherer(parcours, client, acheteur, adhesion.tarif)

    assert not Membership.objects.filter(user=acheteur, price=adhesion.tarif).exists()


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_p20_la_case_newsletter_est_enregistree_sur_l_adhesion(lieu, parcours):
    """Case newsletter cochée : l'adhésion la retient.
    / Newsletter box ticked: the membership keeps it."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="15.00")

    adherer(parcours, client, acheteur, adhesion.tarif, newsletter=True)

    assert adhesion_de(acheteur, adhesion).newsletter is True


# --------------------------------------------------------------------------
# Défauts connus, prouvés et notés (non corrigés dans ce chantier)
# / Known defects, proven and documented (not fixed in this work)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_ressource_a_prix_libre_saisie_a_zero_euro(lieu, parcours):
    """Ressource à prix libre (minimum 0 €), montant saisi 0 € : le créneau est réservé sans
    Stripe, et sa ligne de vente est validée en « offert ».
    / Free-price resource (minimum 0 €), 0 € typed: the slot is booked without Stripe, its
    line valid as "free"."""
    from BaseBillet.models import LigneArticle, PaymentMethod

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="0.00", prix_libre=True)

    debut = location.debut_du_creneau
    donnees_du_formulaire = {
        "resource": str(location.ressource.pk),
        "price_uuid": str(location.tarif.uuid),
        "start_datetime": debut.replace(tzinfo=None).isoformat(),
        "end_time": (debut + timedelta(hours=1)).replace(tzinfo=None).isoformat(),
        f"custom_amount_{location.tarif.uuid}": "0",
        "firstname": "Ada",
        "lastname": "Lovelace",
    }
    if parcours == SANS_PANIER:
        client.post(
            f"/booking/{location.ressource.pk}/book/",
            donnees_du_formulaire,
            **EN_TETE_HTMX,
        )
    else:
        client.post("/panier/add/resource/", donnees_du_formulaire, **EN_TETE_HTMX)
        client.post("/panier/checkout/", **EN_TETE_HTMX)

    booking = booking_de(acheteur, location)
    assert booking is not None
    assert not lieu.stripe.mock_create.called
    ligne = LigneArticle.objects.get(booking=booking)
    assert ligne.status == LigneArticle.VALID
    assert ligne.payment_method == PaymentMethod.FREE


@pytest.mark.parametrize(
    "minimum_du_tarif, montant_saisi",
    [
        ("10.00", "1.00"),   # sous le minimum du tarif / below the price minimum
        ("0.00", "-20.00"),  # négatif : la réservation deviendrait gratuite / negative
        ("0.00", "abc"),     # illisible : ne doit pas donner d'erreur 500 / unreadable
    ],
)
@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_ressource_a_prix_libre_refuse_un_montant_invalide(
    lieu, parcours, minimum_du_tarif, montant_saisi
):
    """Ressource à prix libre : un montant sous le minimum du tarif, négatif ou illisible est
    refusé proprement — aucune réservation, aucun paiement, aucune erreur 500.
    / Free-price resource: an amount below the minimum, negative or unreadable is cleanly
    refused — no booking, no payment, no server error."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix=minimum_du_tarif, prix_libre=True)

    reponse = reserver_une_ressource(
        parcours, client, location, montant_libre=montant_saisi
    )

    verifier_un_refus_propre(parcours, reponse)
    assert booking_de(acheteur, location) is None
    assert not lieu.stripe.mock_create.called


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_ressource_a_prix_libre_sous_le_minimum_stripe_est_refusee(lieu, parcours):
    """Ressource à prix libre (minimum 0 €), 0,30 € pour une heure, sous le minimum Stripe de
    0,50 € : refusée avant le paiement, aucun booking créé. Sans panier, le formulaire
    réaffiché donne la raison.
    / Free-price resource, 0.30 € for one hour (below Stripe's minimum): refused before
    payment, no booking; the direct form shows the reason."""
    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="0.00", prix_libre=True)

    reponse = reserver_une_ressource(parcours, client, location, montant_libre="0.30")

    assert booking_de(acheteur, location) is None
    assert not lieu.stripe.mock_create.called
    if parcours == SANS_PANIER:
        # La langue de la page dépend du lieu : on cherche 0,50 (fr) ou 0.50 (en).
        # / The page language depends on the venue: look for 0,50 (fr) or 0.50 (en).
        page = reponse.content.decode()
        message_d_erreur = page.split('data-testid="booking-error-msg">')[1].split("</div>")[0]
        assert "0,50" in message_d_erreur or "0.50" in message_d_erreur


def test_p2bis_billet_payant_a_zero_euro_pour_un_visiteur_anonyme(lieu):
    """
    Parcours direct d'un visiteur anonyme (le plus fréquent en billetterie), billet « payant »
    à 0 € : pas de Stripe. Le compte créé n'est pas encore activé : la réservation attend
    l'activation (statut gratuit « non activé »), ses billets ne sont pas encore actifs, la
    ligne est validée en « offert ».
    / Anonymous direct flow, paid-category ticket at 0 €: no Stripe; the new account is not
    activated yet, so the reservation waits for activation.
    """
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import LigneArticle, PaymentMethod, Reservation, Ticket

    client_anonyme = client_connecte()
    concert = creer_evenement_avec_tarif(prix="0.00")
    email_du_visiteur = f"test+chantierpanier{identifiant_unique()}@mock.test"

    client_anonyme.post(
        f"/event/{concert.evenement.slug}/reservation/",
        {
            "event": str(concert.evenement.uuid),
            "email": email_du_visiteur,
            str(concert.tarif.uuid): "1",
        },
        **EN_TETE_HTMX,
    )

    visiteur = TibilletUser.objects.get(email=email_du_visiteur)
    reservation = reservation_de(visiteur, concert.evenement)
    assert not lieu.stripe.mock_create.called
    assert reservation.status == Reservation.FREERES
    assert reservation.tickets.get().status == Ticket.NOT_ACTIV
    ligne = LigneArticle.objects.get(reservation=reservation)
    assert ligne.status == LigneArticle.VALID
    assert ligne.payment_method == PaymentMethod.FREE


MONTANT_SAISI_PAR_TARIF_DU_BILLET = {
    "prix_fixe": None,
    "prix_libre": "12.00",
    "prix_libre_a_zero": "0",
}


def reserver_un_billet_gratuit_et_un_payant(
    parcours, client, acheteur, produit_cree_en_premier, tarif_du_billet="prix_fixe"
):
    """
    Même événement, un produit « réservation gratuite » et un produit billet : réserve un
    billet de chaque. L'ordre de création des produits décide l'ordre de traitement (le
    signal de Product donne au nouveau produit un poids plus grand).
    `tarif_du_billet` : "prix_fixe" (10 €), "prix_libre" (12 € saisis) ou
    "prix_libre_a_zero" (0 € saisi). Le panier traite un billet à prix libre à part (son
    propre TicketCreator). Renvoie l'événement.
    / Same event with a free-booking product and a ticket product: books one of each.
    """
    from BaseBillet.models import Price, Product

    if produit_cree_en_premier == "payant":
        concert = creer_evenement_avec_tarif(prix="10.00")
        tarif_payant = concert.tarif
        produit_gratuit = Product.objects.create(
            name=f"TEST_panier gratuit {identifiant_unique()}",
            categorie_article=Product.FREERES,
        )
        concert.evenement.products.add(produit_gratuit)
        tarif_gratuit = produit_gratuit.prices.get(prix=0)
    else:
        concert = creer_evenement_avec_tarif(categorie=Product.FREERES)
        tarif_gratuit = concert.tarif
        produit_payant = Product.objects.create(
            name=f"TEST_panier billet {identifiant_unique()}",
            categorie_article=Product.BILLET,
        )
        concert.evenement.products.add(produit_payant)
        tarif_payant = Price.objects.create(
            product=produit_payant, name="Plein", prix=Decimal("10.00"), publish=True
        )

    montant_saisi = MONTANT_SAISI_PAR_TARIF_DU_BILLET[tarif_du_billet]
    montants_libres = None
    if montant_saisi is not None:
        tarif_payant.free_price = True
        tarif_payant.prix = Decimal("0.00")
        tarif_payant.save(update_fields=["free_price", "prix"])
        montants_libres = {tarif_payant: montant_saisi}

    reserver_des_billets(
        parcours,
        client,
        acheteur,
        concert.evenement,
        {tarif_gratuit: 1, tarif_payant: 1},
        montants_libres=montants_libres,
    )
    return concert.evenement


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize("produit_cree_en_premier", ["payant", "reservation_gratuite"])
@pytest.mark.parametrize("tarif_du_billet", ["prix_fixe", "prix_libre"])
def test_un_evenement_avec_un_produit_gratuit_et_un_payant_active_tous_les_billets(
    lieu, parcours, produit_cree_en_premier, tarif_du_billet
):
    """
    Même événement, un produit « réservation gratuite » et un produit payant : après le retour
    de Stripe, tous les billets de la réservation sont actifs, quel que soit l'ordre des
    produits.
    / Same event, a free-booking product and a paid one: after payment every ticket is active.
    """
    from BaseBillet.models import Ticket

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    evenement = reserver_un_billet_gratuit_et_un_payant(
        parcours, client, acheteur, produit_cree_en_premier, tarif_du_billet
    )
    reservation = reservation_de(acheteur, evenement)
    revenir_de_stripe(client, paiement_des_lignes(reservation=reservation))

    statuts_des_billets = [billet.status for billet in reservation.tickets.all()]
    assert statuts_des_billets == [Ticket.NOT_SCANNED, Ticket.NOT_SCANNED]
    # Les deux billets partent ensemble, dans un seul envoi.
    # / Both tickets are sent together, in a single mail.
    assert noms_des_taches(lieu.taches_demandees).count("ticket_celery_mailer") == 1


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize("produit_cree_en_premier", ["payant", "reservation_gratuite"])
@pytest.mark.parametrize("tarif_du_billet", ["prix_fixe", "prix_libre"])
def test_un_evenement_avec_un_produit_gratuit_et_un_payant_n_envoie_rien_avant_le_paiement(
    lieu, parcours, produit_cree_en_premier, tarif_du_billet
):
    """
    Même événement, un produit « réservation gratuite » et un produit payant, acheteur qui
    n'est pas encore revenu de Stripe : aucun billet actif, aucun envoi de billets, aucun
    webhook « réservation payée ».
    / Same event, free-booking and paid products, buyer not back from Stripe yet: no active
    ticket, no ticket mail, no "reservation paid" webhook.
    """
    from BaseBillet.models import Ticket

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    evenement = reserver_un_billet_gratuit_et_un_payant(
        parcours, client, acheteur, produit_cree_en_premier, tarif_du_billet
    )

    reservation = reservation_de(acheteur, evenement)
    assert not reservation.tickets.filter(status=Ticket.NOT_SCANNED).exists()
    taches_demandees = noms_des_taches(lieu.taches_demandees)
    assert "ticket_celery_mailer" not in taches_demandees
    assert "webhook_reservation" not in taches_demandees


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize("produit_cree_en_premier", ["payant", "reservation_gratuite"])
@pytest.mark.parametrize("tarif_du_billet", ["prix_fixe", "prix_libre"])
def test_un_evenement_avec_un_produit_gratuit_et_un_payant_n_envoie_rien_si_le_paiement_echoue(
    lieu, parcours, produit_cree_en_premier, tarif_du_billet
):
    """
    Même événement, un produit « réservation gratuite » et un produit payant, acheteur revenu
    de Stripe SANS avoir payé : le billet gratuit n'est pas donné seul. Aucun billet actif,
    aucun envoi de billets, aucun webhook ; la réservation attend toujours son paiement.
    / Same event, free-booking and paid products, buyer back from Stripe WITHOUT paying: the
    free ticket is not given alone. No active ticket, no mail, no webhook.
    """
    import time

    from BaseBillet.models import Reservation, Ticket

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    evenement = reserver_un_billet_gratuit_et_un_payant(
        parcours, client, acheteur, produit_cree_en_premier, tarif_du_billet
    )
    reservation = reservation_de(acheteur, evenement)
    lieu.stripe.session.payment_status = "unpaid"
    lieu.stripe.session.status = "open"
    lieu.stripe.session.expires_at = time.time() + 3600

    revenir_de_stripe(client, paiement_des_lignes(reservation=reservation))

    reservation.refresh_from_db()
    assert reservation.status in (Reservation.CREATED, Reservation.UNPAID)
    assert not reservation.tickets.filter(status=Ticket.NOT_SCANNED).exists()
    taches_demandees = noms_des_taches(lieu.taches_demandees)
    assert "ticket_celery_mailer" not in taches_demandees
    assert "webhook_reservation" not in taches_demandees


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize("produit_cree_en_premier", ["payant", "reservation_gratuite"])
def test_un_evenement_avec_un_produit_gratuit_et_un_prix_libre_saisi_a_zero_active_tout(
    lieu, parcours, produit_cree_en_premier
):
    """
    Même événement, un produit « réservation gratuite » et un billet à prix libre saisi à
    0 € : tout est gratuit. Pas de Stripe, les deux billets actifs, un seul envoi.
    / Same event, free-booking product and a free-price ticket entered at 0 €: everything is
    free, both tickets active, a single mail.
    """
    from BaseBillet.models import Ticket

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    evenement = reserver_un_billet_gratuit_et_un_payant(
        parcours, client, acheteur, produit_cree_en_premier, "prix_libre_a_zero"
    )

    reservation = reservation_de(acheteur, evenement)
    assert not lieu.stripe.mock_create.called
    statuts_des_billets = [billet.status for billet in reservation.tickets.all()]
    assert statuts_des_billets == [Ticket.NOT_SCANNED, Ticket.NOT_SCANNED]
    assert noms_des_taches(lieu.taches_demandees).count("ticket_celery_mailer") == 1


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize(
    "produit_cree_en_premier", ["billet_a_zero_euro", "reservation_gratuite"]
)
def test_p2ter_evenement_gratuit_avec_un_produit_freeres_et_un_billet_a_zero_euro(
    lieu, parcours, produit_cree_en_premier
):
    """
    Même événement, un produit « réservation gratuite » et un produit « payant » à 0 € : tout
    est gratuit. Tous les billets sont actifs et envoyés une seule fois, quel que soit l'ordre
    des produits de l'événement (il décide l'ordre de traitement).
    / Same event, a free-booking product and a paid-category one at 0 €: every ticket is
    active and mailed once, whatever the order of the event's products.
    """
    from BaseBillet.models import Price, Product, Ticket

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    if produit_cree_en_premier == "billet_a_zero_euro":
        concert = creer_evenement_avec_tarif(prix="0.00")
        tarif_a_zero_euro = concert.tarif
        produit_gratuit = Product.objects.create(
            name=f"TEST_panier gratuit {identifiant_unique()}",
            categorie_article=Product.FREERES,
        )
        concert.evenement.products.add(produit_gratuit)
        tarif_gratuit = produit_gratuit.prices.get(prix=0)
    else:
        concert = creer_evenement_avec_tarif(categorie=Product.FREERES)
        tarif_gratuit = concert.tarif
        produit_a_zero_euro = Product.objects.create(
            name=f"TEST_panier billet zero {identifiant_unique()}",
            categorie_article=Product.BILLET,
        )
        concert.evenement.products.add(produit_a_zero_euro)
        tarif_a_zero_euro = Price.objects.create(
            product=produit_a_zero_euro, name="Zéro", prix=Decimal("0.00"), publish=True
        )

    reserver_des_billets(
        parcours,
        client,
        acheteur,
        concert.evenement,
        {tarif_gratuit: 1, tarif_a_zero_euro: 1},
    )

    reservation = reservation_de(acheteur, concert.evenement)
    assert not lieu.stripe.mock_create.called
    statuts_des_billets = [billet.status for billet in reservation.tickets.all()]
    assert statuts_des_billets == [Ticket.NOT_SCANNED, Ticket.NOT_SCANNED]
    assert noms_des_taches(lieu.taches_demandees).count("ticket_celery_mailer") == 1


def test_api_v2_un_billet_payant_a_zero_euro_cree_une_seule_ligne_de_vente(
    lieu, api_client, auth_headers
):
    """
    API v2 (troisième parcours, sans panier) : réserver un billet « payant » à 0 € crée UNE
    ligne de vente, pas deux (les exports et les statistiques compteraient double).
    / API v2: booking a paid-category ticket at 0 € creates ONE sale line, not two.
    """
    from BaseBillet.models import LigneArticle, Reservation
    from fabriques_reservation import creer_evenement_et_produit, creer_reservation_api

    event_uuid, price_uuid = creer_evenement_et_produit(
        api_client, auth_headers, identifiant_unique(), price_amount="0.00"
    )
    email = f"test+chantierpanier{identifiant_unique()}@mock.test"

    reponse = creer_reservation_api(
        api_client, auth_headers, event_uuid, price_uuid, email, qty=2
    )

    assert reponse.status_code in (200, 201), reponse.content[:300]
    reservation = Reservation.objects.get(user_commande__email=email)
    assert LigneArticle.objects.filter(reservation=reservation).count() == 1


@pytest.mark.parametrize(
    "etat_de_l_evenement, reservation_attendue",
    [
        ("en_cours_jusqu_a_demain", True),
        ("archive", True),
        ("termine", False),
        ("commence_depuis_2_jours_sans_date_de_fin", False),
    ],
)
def test_api_v2_vend_jusqu_a_la_fin_de_l_evenement(
    lieu, api_client, auth_headers, etat_de_l_evenement, reservation_attendue
):
    """
    API v2 (et caisse) : même règle de date que le front, sans contrôle archivé/dépublié.
    Un festival en cours (commencé il y a 3 jours) ou un événement archivé mais pas terminé
    est vendu ; un événement terminé est refusé.
    / API v2 (and POS): same date rule as the front, without the archived check.
    """
    from test_panier_session import mettre_l_evenement_dans_l_etat

    from BaseBillet.models import Reservation

    concert = creer_evenement_avec_tarif(prix="0.00")
    mettre_l_evenement_dans_l_etat(concert, etat_de_l_evenement)
    email = f"test+chantierpanier{identifiant_unique()}@mock.test"

    from fabriques_reservation import creer_reservation_api

    reponse = creer_reservation_api(
        api_client,
        auth_headers,
        str(concert.evenement.uuid),
        str(concert.tarif.uuid),
        email,
    )

    reservation_creee = Reservation.objects.filter(user_commande__email=email).exists()
    assert reservation_creee == reservation_attendue, reponse.content[:300]
    if not reservation_attendue:
        assert reponse.status_code == 400


@pytest.mark.parametrize("produit_cree_en_premier", ["payant", "reservation_gratuite"])
def test_api_v2_vente_en_caisse_d_un_evenement_mixte_active_tous_les_billets(
    lieu, api_client, auth_headers, produit_cree_en_premier
):
    """
    Caisse LaBoutik (API v2, payé en espèces) : même événement, une « réservation gratuite » et
    un billet à 10 €, un de chaque. La vente est déjà payée : tous les billets sont actifs,
    quel que soit l'ordre des produits.
    / POS sale (API v2, cash) of a free booking + a 10 € ticket: every ticket is active.
    """
    import json

    from BaseBillet.models import Price, Product, Reservation, Ticket

    if produit_cree_en_premier == "payant":
        concert = creer_evenement_avec_tarif(prix="10.00")
        tarif_payant = concert.tarif
        produit_gratuit = Product.objects.create(
            name=f"TEST_panier gratuit {identifiant_unique()}",
            categorie_article=Product.FREERES,
        )
        concert.evenement.products.add(produit_gratuit)
        tarif_gratuit = produit_gratuit.prices.get(prix=0)
    else:
        concert = creer_evenement_avec_tarif(categorie=Product.FREERES)
        tarif_gratuit = concert.tarif
        produit_payant = Product.objects.create(
            name=f"TEST_panier billet {identifiant_unique()}",
            categorie_article=Product.BILLET,
        )
        concert.evenement.products.add(produit_payant)
        tarif_payant = Price.objects.create(
            product=produit_payant, name="Plein", prix=Decimal("10.00"), publish=True
        )
    email = f"test+chantierpanier{identifiant_unique()}@mock.test"

    reponse = api_client.post(
        "/api/v2/reservations/",
        data=json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Reservation",
                "reservationFor": {
                    "@type": "Event",
                    "identifier": str(concert.evenement.uuid),
                },
                "underName": {"@type": "Person", "email": email},
                "reservedTicket": [
                    {
                        "@type": "Ticket",
                        "identifier": str(tarif_gratuit.uuid),
                        "ticketQuantity": 1,
                    },
                    {
                        "@type": "Ticket",
                        "identifier": str(tarif_payant.uuid),
                        "ticketQuantity": 1,
                    },
                ],
                "additionalProperty": [
                    {
                        "@type": "PropertyValue",
                        "name": "paymentMethod",
                        "value": "cash",
                    },
                ],
            }
        ),
        content_type="application/json",
        **auth_headers,
    )

    assert reponse.status_code in (200, 201), reponse.content[:300]
    reservation = Reservation.objects.get(user_commande__email=email)
    assert not lieu.stripe.mock_create.called
    statuts_des_billets = [billet.status for billet in reservation.tickets.all()]
    assert statuts_des_billets == [Ticket.NOT_SCANNED, Ticket.NOT_SCANNED]


def test_api_v2_reservation_gratuite_et_billet_a_zero_euro_ont_chacun_leur_ligne_de_vente(
    lieu, api_client, auth_headers
):
    """
    API v2 : même événement, un produit « réservation gratuite » et un billet « payant » à
    0 €, un de chaque. Chaque tarif a SA ligne de vente, une seule : celle du billet (créée par
    TicketCreator) et celle de la réservation gratuite (créée par l'API).
    / API v2: free booking + 0 € ticket on the same event: each price has exactly one line.
    """
    import json

    from BaseBillet.models import LigneArticle, Product, Reservation

    concert = creer_evenement_avec_tarif(categorie=Product.FREERES)
    tarif_gratuit = concert.tarif
    produit_a_zero_euro = Product.objects.create(
        name=f"TEST_panier billet zero {identifiant_unique()}",
        categorie_article=Product.BILLET,
    )
    concert.evenement.products.add(produit_a_zero_euro)
    tarif_a_zero_euro = ajouter_un_tarif(produit_a_zero_euro, prix="0.00", nom="Zéro")
    email = f"test+chantierpanier{identifiant_unique()}@mock.test"

    reponse = api_client.post(
        "/api/v2/reservations/",
        data=json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Reservation",
                "reservationFor": {
                    "@type": "Event",
                    "identifier": str(concert.evenement.uuid),
                },
                "underName": {"@type": "Person", "email": email},
                "reservedTicket": [
                    {
                        "@type": "Ticket",
                        "identifier": str(tarif_gratuit.uuid),
                        "ticketQuantity": 1,
                    },
                    {
                        "@type": "Ticket",
                        "identifier": str(tarif_a_zero_euro.uuid),
                        "ticketQuantity": 1,
                    },
                ],
            }
        ),
        content_type="application/json",
        **auth_headers,
    )

    assert reponse.status_code in (200, 201), reponse.content[:300]
    reservation = Reservation.objects.get(user_commande__email=email)
    tarifs_des_lignes = sorted(
        str(ligne.pricesold.price.uuid)
        for ligne in LigneArticle.objects.filter(reservation=reservation)
    )
    assert tarifs_des_lignes == sorted(
        [str(tarif_gratuit.uuid), str(tarif_a_zero_euro.uuid)]
    )


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize(
    "tarif_demande, quantite, reservation_attendue",
    [
        ("avec_repas", 1, False),
        ("sans_repas", 1, True),
        ("sans_repas", 2, False),
    ],
)
def test_jauge_de_l_evenement_et_repas_limite_avec_deux_produits_exclusifs(
    lieu, parcours, tarif_demande, quantite, reservation_attendue
):
    """
    Cas d'usage d'un lieu : un repas limité dans un événement à jauge. Deux produits
    exclusifs, « réservation avec repas » (stock 1) et « réservation sans repas » (sans stock),
    jauge de l'événement : 4 personnes. Déjà vendus : 1 avec repas + 2 sans repas (3 personnes).
    - 1 avec repas : refusé (le repas est épuisé) ;
    - 1 sans repas : accepté (4e personne) ;
    - 2 sans repas : refusé (5 personnes pour une jauge de 4).
    Une personne = un billet : la jauge compte les deux produits, le stock ne compte que le
    tarif avec repas. Pas de doublon.
    / A venue's use case: limited meals in a capacity-limited event, two exclusive products.
    """
    from BaseBillet.models import Product

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    avec_repas = creer_evenement_avec_tarif(prix="20.00", jauge_max=4, stock_du_tarif=1)
    produit_sans_repas = Product.objects.create(
        name=f"TEST_panier sans repas {identifiant_unique()}",
        categorie_article=Product.BILLET,
    )
    avec_repas.evenement.products.add(produit_sans_repas)
    sans_repas = SimpleNamespace(
        evenement=avec_repas.evenement,
        produit=produit_sans_repas,
        tarif=ajouter_un_tarif(produit_sans_repas, prix="10.00", nom="Sans repas"),
    )
    creer_un_billet_deja_vendu(creer_utilisateur(), avec_repas)
    creer_un_billet_deja_vendu(creer_utilisateur(), sans_repas)
    creer_un_billet_deja_vendu(creer_utilisateur(), sans_repas)
    tarif = avec_repas.tarif if tarif_demande == "avec_repas" else sans_repas.tarif

    with configuration_modifiee(allow_concurrent_bookings=True):
        reserver_des_billets(
            parcours, client, acheteur, avec_repas.evenement, {tarif: quantite}
        )

    reservation_creee = reservation_de(acheteur, avec_repas.evenement) is not None
    assert reservation_creee == reservation_attendue


def reserver_deux_reservations_gratuites(parcours, client, acheteur):
    """
    Même événement, deux produits « réservation gratuite » (avec repas, sans repas) : une
    place de chaque dans la même commande. Renvoie l'événement.
    / Same event, two free-booking products: one seat of each in the same order.
    """
    from BaseBillet.models import Product

    avec_repas = creer_evenement_avec_tarif(categorie=Product.FREERES)
    produit_sans_repas = Product.objects.create(
        name=f"TEST_panier sans repas {identifiant_unique()}",
        categorie_article=Product.FREERES,
    )
    avec_repas.evenement.products.add(produit_sans_repas)
    reserver_des_billets(
        parcours,
        client,
        acheteur,
        avec_repas.evenement,
        {avec_repas.tarif: 1, produit_sans_repas.prices.get(prix=0): 1},
    )
    return avec_repas.evenement


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_deux_reservations_gratuites_dans_une_commande_n_envoient_les_billets_qu_une_fois(
    lieu, parcours
):
    """
    Deux produits « réservation gratuite », une place de chaque dans la même commande : les
    deux billets sont actifs, envoyés en UN seul mail, et le webhook « réservation » part une
    seule fois.
    / Two free-booking products in one order: both tickets active, one mail, one webhook.
    """
    from BaseBillet.models import Ticket

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    evenement = reserver_deux_reservations_gratuites(parcours, client, acheteur)

    reservation = reservation_de(acheteur, evenement)
    statuts_des_billets = [billet.status for billet in reservation.tickets.all()]
    assert statuts_des_billets == [Ticket.NOT_SCANNED, Ticket.NOT_SCANNED]
    taches_demandees = noms_des_taches(lieu.taches_demandees)
    assert taches_demandees.count("ticket_celery_mailer") == 1
    assert taches_demandees.count("webhook_reservation") == 1


def test_deux_reservations_gratuites_d_un_visiteur_non_active_attendent_l_activation(
    lieu,
):
    """
    Visiteur anonyme (compte pas encore activé), deux produits « réservation gratuite » dans
    la même commande directe : aucun envoi, la réservation attend la confirmation de l'email.
    / Anonymous visitor, two free-booking products: nothing sent, waits for email confirmation.
    """
    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Product, Reservation, Ticket

    client_anonyme = client_connecte()
    email_du_visiteur = f"test+chantierpanier{identifiant_unique()}@mock.test"
    avec_repas = creer_evenement_avec_tarif(categorie=Product.FREERES)
    produit_sans_repas = Product.objects.create(
        name=f"TEST_panier sans repas {identifiant_unique()}",
        categorie_article=Product.FREERES,
    )
    avec_repas.evenement.products.add(produit_sans_repas)
    client_anonyme.post(
        f"/event/{avec_repas.evenement.slug}/reservation/",
        {
            "event": str(avec_repas.evenement.uuid),
            "email": email_du_visiteur,
            str(avec_repas.tarif.uuid): "1",
            str(produit_sans_repas.prices.get(prix=0).uuid): "1",
        },
        **EN_TETE_HTMX,
    )

    visiteur = TibilletUser.objects.get(email=email_du_visiteur)
    reservation = reservation_de(visiteur, avec_repas.evenement)
    assert reservation.status == Reservation.FREERES
    assert not reservation.tickets.filter(status=Ticket.NOT_SCANNED).exists()
    assert "ticket_celery_mailer" not in noms_des_taches(lieu.taches_demandees)


# --------------------------------------------------------------------------
# Paiement en cours : une place est retenue 30 minutes (DUREE_D_UN_PAIEMENT_EN_COURS)
# / Payment in progress: a seat is held for 30 minutes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize(
    "depuis_minutes, reservation_attendue", [(20, False), (40, True)]
)
def test_un_paiement_en_cours_retient_sa_place_dans_le_stock_du_tarif(
    lieu, parcours, depuis_minutes, reservation_attendue
):
    """Stock du tarif : 1, pris par un paiement en cours. Commencé il y a 20 minutes : la
    place est retenue, la demande est refusée. Il y a 40 minutes : la place est libérée.
    / Price stock 1, held by a payment in progress: held for 30 minutes, then freed."""
    from fabriques_panier import creer_un_billet_en_cours_de_paiement

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00", stock_du_tarif=1)
    creer_un_billet_en_cours_de_paiement(creer_utilisateur(), concert, depuis_minutes)

    reserver_des_billets(
        parcours, client, acheteur, concert.evenement, {concert.tarif: 1}
    )

    assert (
        reservation_de(acheteur, concert.evenement) is not None
    ) == reservation_attendue


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize(
    "adhesion_qui_occupe_la_place, adhesion_attendue",
    [
        ("paiement_en_cours_depuis_20_min", False),
        ("paiement_en_cours_depuis_40_min", True),
        ("validation_manuelle_en_attente", False),
    ],
)
def test_une_adhesion_en_cours_retient_sa_place_dans_le_stock(
    lieu, parcours, adhesion_qui_occupe_la_place, adhesion_attendue
):
    """Tarif d'adhésion au stock de 1, occupé par une autre adhésion : en attente de
    paiement depuis 20 minutes (retenue), depuis 40 minutes (libérée), ou en attente de
    validation manuelle (retenue).
    / Membership price with a stock of 1, held by another membership in progress."""
    from datetime import timedelta as duree

    from BaseBillet.models import Membership

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    adhesion = creer_adhesion(prix="15.00")
    adhesion.tarif.stock = 1
    adhesion.tarif.save()
    if adhesion_qui_occupe_la_place == "validation_manuelle_en_attente":
        Membership.objects.create(
            user=creer_utilisateur(),
            price=adhesion.tarif,
            status=Membership.ADMIN_WAITING,
        )
    else:
        minutes = 20 if adhesion_qui_occupe_la_place.endswith("20_min") else 40
        autre_adhesion = Membership.objects.create(
            user=creer_utilisateur(),
            price=adhesion.tarif,
            status=Membership.WAITING_PAYMENT,
        )
        Membership.objects.filter(pk=autre_adhesion.pk).update(
            date_added=timezone.now() - duree(minutes=minutes)
        )

    adherer(parcours, client, acheteur, adhesion.tarif)

    adhesion_creee = Membership.objects.filter(
        user=acheteur, price=adhesion.tarif
    ).exists()
    assert adhesion_creee == adhesion_attendue


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
@pytest.mark.parametrize("depuis_minutes, booking_attendu", [(20, False), (40, True)])
def test_un_creneau_en_cours_de_paiement_retient_sa_place(
    lieu, parcours, depuis_minutes, booking_attendu
):
    """Ressource de capacité 1 : le même créneau est pris par une réservation en attente de
    paiement. Depuis 20 minutes : retenu, la demande est refusée. Depuis 40 minutes : libéré.
    / Capacity-1 resource, same slot held by a booking waiting for payment for 30 minutes."""
    from datetime import timedelta as duree

    from booking.models import Booking

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="12.00", capacite=1)
    # Un autre utilisateur réserve le même créneau par le vrai formulaire (le formulaire lit
    # l'heure dans le fuseau du lieu) : son booking attend le paiement.
    # / Another user books the same slot through the real form: waiting for payment.
    autre_utilisateur = creer_utilisateur()
    reserver_une_ressource(SANS_PANIER, client_connecte(autre_utilisateur), location)
    autre_booking = Booking.objects.get(
        user=autre_utilisateur, resource=location.ressource
    )
    assert autre_booking.status == Booking.WAITING_PAYMENT
    Booking.objects.filter(pk=autre_booking.pk).update(
        booked_at=timezone.now() - duree(minutes=depuis_minutes)
    )

    reserver_une_ressource(parcours, client, location)

    assert (booking_de(acheteur, location) is not None) == booking_attendu


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_un_creneau_reserve_gratuitement_reste_pris_avant_activation(lieu, parcours):
    """Ressource de capacité 1 : le créneau est déjà pris par une réservation gratuite dont la
    personne n'a pas encore validé son adresse mail. La place est retenue, la demande suivante
    est refusée — comme pour une réservation gratuite déjà activée.
    / Capacity-1 resource: the slot is held by a free booking whose owner has not verified
    their email yet. The slot stays taken."""
    from booking.models import Booking

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    location = creer_ressource_avec_tarif(prix="12.00", capacite=1)
    # Une autre personne prend le créneau par le vrai formulaire (lui seul lit l'heure dans le
    # fuseau du lieu), puis sa réservation est mise en « attente de validation du mail ».
    # / Another person takes the slot through the real form (only it reads the venue timezone),
    # then their booking is moved to "email verification pending".
    autre_utilisateur = creer_utilisateur()
    reserver_une_ressource(SANS_PANIER, client_connecte(autre_utilisateur), location)
    Booking.objects.filter(
        user=autre_utilisateur, resource=location.ressource
    ).update(status=Booking.FREERES)

    reserver_une_ressource(parcours, client, location)

    assert booking_de(acheteur, location) is None


def test_la_caisse_compte_les_billets_en_cours_de_paiement_pendant_30_minutes(lieu):
    """Caisse LaBoutik : un billet en cours de paiement depuis 20 minutes compte dans les
    achats en cours de l'événement (affichage « complet »).
    / POS: a ticket in progress for 20 minutes counts as being purchased."""
    from fabriques_panier import creer_un_billet_en_cours_de_paiement
    from laboutik.views import _charger_events_billetterie

    concert = creer_evenement_avec_tarif(prix="10.00")
    creer_un_billet_en_cours_de_paiement(
        creer_utilisateur(), concert, depuis_minutes=20
    )

    evenements, _compteur = _charger_events_billetterie()

    evenement_charge = [e for e in evenements if e.pk == concert.evenement.pk][0]
    assert evenement_charge.nb_en_cours_achat == 1


def test_une_reservation_gratuite_confirmee_apres_20_minutes_reste_valide(lieu):
    """
    Visiteur anonyme, événement gratuit à une place : il confirme son email 20 minutes
    après sa réservation. Sa place était retenue (moins de 30 minutes) : la réservation est
    validée, pas annulée pour « événement complet » (sa propre place ne compte pas deux fois).
    / Anonymous visitor confirms 20 minutes later: the held seat is his, booking confirmed.
    """
    from datetime import timedelta as duree

    from AuthBillet.models import TibilletUser
    from BaseBillet.models import Product, Reservation

    client_anonyme = client_connecte()
    concert = creer_evenement_avec_tarif(categorie=Product.FREERES, jauge_max=1)
    email_du_visiteur = f"test+chantierpanier{identifiant_unique()}@mock.test"
    client_anonyme.post(
        f"/event/{concert.evenement.slug}/reservation/",
        {
            "event": str(concert.evenement.uuid),
            "email": email_du_visiteur,
            str(concert.tarif.uuid): "1",
        },
        **EN_TETE_HTMX,
    )
    visiteur = TibilletUser.objects.get(email=email_du_visiteur)
    reservation = reservation_de(visiteur, concert.evenement)
    assert reservation.status == Reservation.FREERES
    Reservation.objects.filter(pk=reservation.pk).update(
        datetime=timezone.now() - duree(minutes=20)
    )

    visiteur.is_active = True
    visiteur.save()

    reservation.refresh_from_db()
    assert reservation.status == Reservation.FREERES_USERACTIV


@pytest.mark.parametrize("parcours", LES_DEUX_PARCOURS)
def test_la_session_stripe_expire_apres_30_minutes(lieu, parcours):
    """La session de paiement Stripe expire 30 minutes après sa création (plus une minute de
    marge : Stripe refuse moins de 30 minutes), comme la place retenue.
    / The Stripe session expires 30 minutes after creation (plus one minute of margin)."""
    import time

    acheteur = creer_utilisateur()
    client = client_connecte(acheteur)
    concert = creer_evenement_avec_tarif(prix="10.00")

    avant = time.time()
    reserver_des_billets(
        parcours, client, acheteur, concert.evenement, {concert.tarif: 1}
    )
    apres = time.time()

    expiration = lieu.stripe.mock_create.call_args.kwargs["expires_at"]
    assert avant + 30 * 60 <= expiration <= apres + 32 * 60


# --------------------------------------------------------------------------
# Interface de la réservation d'une ressource et lien du panier
# / Resource booking interface and cart link
# --------------------------------------------------------------------------


def test_le_panneau_de_reservation_d_une_ressource_s_intitule_reserver(lieu):
    """Page d'une ressource : le panneau qui s'ouvre au clic sur un créneau s'intitule
    « Réserver ».
    / Resource page: the panel opened by a slot click is titled "Réserver"."""
    client = client_connecte(creer_utilisateur())
    location = creer_ressource_avec_tarif()

    reponse = client.get(
        f"/booking/{location.ressource.pk}/resource/", HTTP_ACCEPT_LANGUAGE="fr"
    )

    page = reponse.content.decode()
    titre_du_panneau = page.split('id="bookingPanelLabel">')[1].split("</h5>")[0]
    assert titre_du_panneau.strip() == "Réserver"


def test_le_formulaire_d_une_ressource_a_un_seul_tarif_le_coche_d_office(lieu):
    """Formulaire d'une ressource qui n'a qu'un tarif : ce tarif est déjà coché, et le
    bouton de paiement direct s'intitule « Payer maintenant ».
    / Form of a single-price resource: the price is pre-checked, the direct payment button
    reads "Payer maintenant"."""
    client = client_connecte(creer_utilisateur())
    location = creer_ressource_avec_tarif()

    reponse = client.get(
        f"/booking/{location.ressource.pk}/book/",
        {"start_datetime": location.debut_du_creneau.replace(tzinfo=None).isoformat()},
        HTTP_ACCEPT_LANGUAGE="fr",
        **EN_TETE_HTMX,
    )

    page = reponse.content.decode()
    bouton_radio_du_tarif = page.split(f'id="price-{location.tarif.uuid}"')[1].split(
        ">"
    )[0]
    assert "checked" in bouton_radio_du_tarif
    bouton_payer = page.split('data-testid="resource-submit"')[1].split("</button>")[0]
    assert "Payer maintenant" in bouton_payer


@pytest.mark.parametrize("skin", ["reunion", "V2", "faire_festival"])
def test_le_lien_du_panier_du_menu_est_decrit_par_sa_pastille(lieu, skin):
    """Menu de chaque skin : le lien du panier s'appelle « Panier » et il est décrit par la
    pastille #panier-badge-nav, que HTMX remplace après chaque ajout. Un lecteur d'écran
    annonce donc le nombre d'articles à jour, en français.
    / Every skin's menu: the cart link is named "Panier" and described by the badge that HTMX
    replaces after each addition, so screen readers announce an up-to-date count."""
    client = client_connecte(creer_utilisateur())
    location = creer_ressource_avec_tarif()

    with patch("BaseBillet.views.get_skin_courant", return_value=skin):
        reponse = client.get(
            f"/booking/{location.ressource.pk}/resource/", HTTP_ACCEPT_LANGUAGE="fr"
        )

    page = reponse.content.decode()
    lien_du_panier = page.split('href="/panier/"')[1].split(">")[0]
    assert 'aria-label="Panier"' in lien_du_panier
    assert 'aria-describedby="panier-badge-nav"' in lien_du_panier
