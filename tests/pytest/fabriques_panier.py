"""
Fabriques et simulations pour les tests du panier (et de la parité avec / sans panier).
/ Factories and fakes for the cart tests (and the with / without cart parity tests).

LOCALISATION : tests/pytest/fabriques_panier.py

Ce module n'est pas un fichier de tests (pas de préfixe test_) : pytest ne le collecte pas.
Les fichiers de tests l'importent : `from fabriques_panier import ...`.
/ Not a test file (no test_ prefix): pytest does not collect it. Test files import it.

Les fabriques créent les objets par l'ORM. Elles sont appelées DANS un test marqué
`@pytest.mark.django_db` et DANS un `tenant_context` : pytest-django annule la transaction
à la fin du test, rien ne reste en base de dev. Aucune fabrique ne supprime quoi que ce soit.
/ Factories create objects through the ORM, inside a `django_db` test and a
`tenant_context`: pytest-django rolls the transaction back, nothing stays in the dev DB.

Trois simulations sont indispensables, parce que certains effets sortent de la transaction
et ne seraient pas annulés par le rollback :
- Fedow : créer un produit adhésion appelle Fedow en HTTP (signal post_save de Product) ;
- Stripe : le catalogue (`stripe.Product`, `stripe.Price`) est appelé pour toute ligne de
  vente qui n'est pas une réservation gratuite, même à 0 € ;
- Celery : chaque `.delay()` enverrait une tâche au vrai worker, sur des objets qui
  n'existeront plus après le rollback.
/ Three fakes are required, because some effects escape the transaction: Fedow HTTP on
membership product creation, the Stripe catalogue, and Celery tasks sent to the real worker.
"""

import uuid
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

PREFIXE_DE_TEST = "TEST_panier"


def identifiant_unique():
    """8 caractères pour rendre uniques les noms et les emails de test.
    / 8 characters to make test names and emails unique."""
    return uuid.uuid4().hex[:8]


# --------------------------------------------------------------------------
# Simulations (Stripe, Celery, Configuration)
# / Fakes (Stripe, Celery, Configuration)
# --------------------------------------------------------------------------


@contextmanager
def catalogue_stripe_simule():
    """
    Remplace les appels au catalogue Stripe (produits et prix) par des faux.
    / Replaces Stripe catalogue calls (products and prices) with fakes.

    `mock_stripe` (conftest) ne simule que la session de paiement. Or chaque ligne de vente
    qui n'est pas une réservation gratuite demande un identifiant de prix Stripe
    (`PriceSold.get_id_price_stripe`), même à 0 €. Sans ce patch, le test appellerait le
    vrai Stripe en mode test.
    / `mock_stripe` only fakes the checkout session. Every sale line asks Stripe for a
    price id, even at 0 €. Without this patch the test would call the real Stripe API.

    Rend un objet avec les trois faux, pour vérifier s'ils ont été appelés.
    / Yields the three fakes, to check whether they were called.
    """
    faux_produit_stripe = MagicMock(id="prod_test_panier")
    faux_prix_stripe = MagicMock(id="price_test_panier")
    with (
        patch(
            "stripe.Product.retrieve", return_value=faux_produit_stripe
        ) as faux_retrieve,
        patch(
            "stripe.Product.create", return_value=faux_produit_stripe
        ) as faux_product_create,
        patch(
            "stripe.Price.create", return_value=faux_prix_stripe
        ) as faux_price_create,
    ):
        yield SimpleNamespace(
            product_retrieve=faux_retrieve,
            product_create=faux_product_create,
            price_create=faux_price_create,
        )


@contextmanager
def taches_celery_enregistrees():
    """
    Intercepte toutes les tâches Celery demandées, sans les envoyer au worker.
    / Intercepts every requested Celery task, without sending it to the worker.

    `.delay(...)` appelle `Task.apply_async(...)`. On remplace `apply_async` sur la classe de
    base : toutes les tâches du projet en héritent. `autospec=True` garde `self`, donc le
    nom de la tâche.
    / `.delay()` calls `Task.apply_async()`. Patching the base class catches every task;
    `autospec=True` keeps `self`, hence the task name.

    Rend une liste de `(nom_court_de_la_tache, arguments)`, remplie au fil du test.
    Exemple : `("send_membership_invoice_to_email", ("<uuid>",))`.
    / Yields a list of `(short task name, args)`, filled as the test runs.
    """
    from celery.app.task import Task

    taches_demandees = []

    def enregistrer_la_tache(tache, args=None, kwargs=None, **options):
        nom_court_de_la_tache = tache.name.split(".")[-1]
        taches_demandees.append((nom_court_de_la_tache, tuple(args or ())))
        return MagicMock()

    with patch.object(
        Task, "apply_async", autospec=True, side_effect=enregistrer_la_tache
    ):
        yield taches_demandees


def noms_des_taches(taches_demandees):
    """Liste des noms courts des tâches demandées, dans l'ordre.
    / Short names of the requested tasks, in order."""
    noms = []
    for nom_de_la_tache, _arguments in taches_demandees:
        noms.append(nom_de_la_tache)
    return noms


@contextmanager
def configuration_modifiee(**valeurs):
    """
    Change des réglages de `Configuration` le temps d'un test, sans jamais l'enregistrer.
    / Changes `Configuration` settings for one test, without ever saving it.

    `Configuration` est un singleton mis en cache (django-solo, memcached). Un `save()` ou un
    `update()` dans un test mettrait la valeur en cache pour le serveur live aussi, et le
    rollback ne l'annulerait pas. On patche donc `get_solo()` pour qu'il rende toujours la
    même instance, modifiée en mémoire.
    / `Configuration` is a cached singleton: a save or update in a test would leak to the live
    server. `get_solo()` is patched to always return the same in-memory instance.

    Exemple : `with configuration_modifiee(allow_concurrent_bookings=False): ...`
    """
    from BaseBillet.models import Configuration

    configuration_du_test = Configuration.get_solo()
    for nom_du_reglage, valeur in valeurs.items():
        setattr(configuration_du_test, nom_du_reglage, valeur)

    with patch.object(Configuration, "get_solo", return_value=configuration_du_test):
        yield configuration_du_test


# --------------------------------------------------------------------------
# Utilisateurs, requêtes, clients
# / Users, requests, clients
# --------------------------------------------------------------------------


def creer_utilisateur(actif=True, prenom="Test", nom="Panier"):
    """
    Crée un utilisateur de test, email en minuscules et unique.
    / Creates a test user, with a unique lowercase email.
    """
    from AuthBillet.models import TibilletUser

    email = f"test+chantierpanier{identifiant_unique()}@mock.test"
    utilisateur = TibilletUser.objects.create(
        email=email,
        username=email,
        first_name=prenom,
        last_name=nom,
        is_active=actif,
    )
    return utilisateur


def requete_avec_session(utilisateur=None):
    """
    Requête minimale avec une session et un utilisateur, pour appeler `PanierSession`
    sans passer par une vue (tests/PIEGES.md, pièges 10.2 et 10.3).
    / Minimal request with a session and a user, to call `PanierSession` directly.

    Sans utilisateur : `AnonymousUser`.
    """
    from django.contrib.auth.models import AnonymousUser
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.test import RequestFactory

    requete = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(requete)
    requete.session.save()
    if utilisateur is None:
        requete.user = AnonymousUser()
    else:
        requete.user = utilisateur
    return requete


def client_connecte(utilisateur=None):
    """
    Client de test Django sur le tenant `lespass`, connecté si un utilisateur est donné.
    / Django test client on the `lespass` tenant, logged in when a user is given.

    Un client neuf par test : la session de `force_login` est écrite en base, et le rollback
    de fin de test l'efface. Un client partagé entre tests redeviendrait anonyme en silence.
    `HTTP_ACCEPT_LANGUAGE="en"` : les messages sont rendus en anglais, comme les textes
    source du panier.
    / A fresh client per test: the force_login session lives in the DB and is rolled back.
    """
    from django.test import Client

    client = Client(HTTP_HOST="lespass.tibillet.localhost", HTTP_ACCEPT_LANGUAGE="en")
    if utilisateur is not None:
        client.force_login(utilisateur)
    return client


# --------------------------------------------------------------------------
# Produits : billetterie, adhésion, ressource
# / Products: tickets, membership, resource
# --------------------------------------------------------------------------


def creer_evenement_avec_tarif(
    prix="10.00",
    categorie=None,
    jauge_max=100,
    jours_avant_l_evenement=7,
    duree_en_heures=2,
    max_par_personne_evenement=None,
    max_par_personne_produit=None,
    max_par_personne_tarif=None,
    stock_du_tarif=None,
    prix_libre=False,
):
    """
    Crée un événement, un produit billet lié, et un tarif publié.
    / Creates an event, a linked ticket product, and a published price.

    `categorie` : `Product.BILLET` par défaut (payant ; à 0 € il est gratuit, sans Stripe).
    Avec `Product.FREERES` (réservation gratuite), le tarif à 0 € est créé automatiquement
    par le signal post_save de Product : on le réutilise (piège 12.16).
    / Default category is paid tickets. With FREERES, the 0 € price is auto-created.

    Rend un objet avec `evenement`, `produit`, `tarif`.
    """
    from django.utils import timezone
    from BaseBillet.models import Event, Price, Product

    if categorie is None:
        categorie = Product.BILLET

    identifiant = identifiant_unique()
    debut = timezone.now() + timedelta(days=jours_avant_l_evenement)
    evenement = Event.objects.create(
        name=f"{PREFIXE_DE_TEST} evenement {identifiant}",
        datetime=debut,
        end_datetime=debut + timedelta(hours=duree_en_heures),
        jauge_max=jauge_max,
        max_per_user=max_par_personne_evenement,
    )
    produit = Product.objects.create(
        name=f"{PREFIXE_DE_TEST} billet {identifiant}",
        categorie_article=categorie,
        max_per_user=max_par_personne_produit,
    )
    evenement.products.add(produit)

    if categorie == Product.FREERES:
        tarif = produit.prices.get(prix=0)
    else:
        tarif = Price.objects.create(
            product=produit,
            name="Plein tarif",
            prix=Decimal(prix),
            publish=True,
            max_per_user=max_par_personne_tarif,
            stock=stock_du_tarif,
            free_price=prix_libre,
        )

    return SimpleNamespace(evenement=evenement, produit=produit, tarif=tarif)


def ajouter_un_tarif(produit, prix="5.00", nom="Tarif réduit", **autres_champs):
    """Ajoute un tarif publié à un produit existant.
    / Adds a published price to an existing product."""
    from BaseBillet.models import Price

    return Price.objects.create(
        product=produit,
        name=nom,
        prix=Decimal(prix),
        publish=True,
        **autres_champs,
    )


def creer_adhesion(
    prix="15.00",
    prix_libre=False,
    recurrente=False,
    validation_manuelle=False,
    max_par_personne=None,
):
    """
    Crée un produit adhésion et un tarif annuel publié.
    / Creates a membership product and a published yearly price.

    Le signal post_save de Product appelle Fedow en HTTP pour déclarer l'adhésion. Cet appel
    sort de la transaction : on le simule le temps de la création.
    / Product's post_save signal calls Fedow over HTTP: it is faked during creation.

    Rend un objet avec `produit` et `tarif`.
    """
    from BaseBillet.models import Price, Product

    identifiant = identifiant_unique()
    with patch("BaseBillet.signals.AssetFedow") as fedow_simule:
        # Le signal attend un couple (asset, créé) : on le lui donne, sinon il journalise
        # une erreur Fedow (non bloquante) qui brouillerait la lecture des logs.
        # / The signal expects an (asset, created) pair: give it, to keep logs clean.
        fedow_simule.return_value.get_or_create_membership_asset.return_value = (
            MagicMock(),
            True,
        )
        produit = Product.objects.create(
            name=f"{PREFIXE_DE_TEST} adhesion {identifiant}",
            categorie_article=Product.ADHESION,
        )
    tarif = Price.objects.create(
        product=produit,
        name="Adhésion annuelle",
        prix=Decimal(prix),
        publish=True,
        subscription_type=Price.YEAR,
        free_price=prix_libre,
        recurring_payment=recurrente,
        manual_validation=validation_manuelle,
        max_per_user=max_par_personne,
    )
    return SimpleNamespace(produit=produit, tarif=tarif)


def creer_ressource_avec_tarif(prix="12.00", capacite=1, prix_libre=False):
    """
    Crée une ressource réservable tous les jours de 10 h à 18 h (créneaux d'une heure),
    avec son produit (catégorie ressource) et un tarif horaire publié.
    / Creates a resource bookable every day from 10:00 to 18:00 (one-hour slots), with its
    product (resource category) and a published hourly price.

    Rend un objet avec `ressource`, `produit`, `tarif`, et `debut_du_creneau` : un créneau
    libre dans deux jours, à 10 h (fuseau courant).
    / Also yields `debut_du_creneau`: a free slot in two days at 10:00 (current timezone).
    """
    import datetime

    from django.utils import timezone
    from BaseBillet.models import Price, Product
    from booking.models import Calendar, OpeningEntry, Resource, WeeklyOpening

    identifiant = identifiant_unique()
    calendrier = Calendar.objects.create(
        name=f"{PREFIXE_DE_TEST} calendrier {identifiant}"
    )
    ouverture_hebdomadaire = WeeklyOpening.objects.create(
        name=f"{PREFIXE_DE_TEST} ouverture {identifiant}",
    )
    for jour_de_la_semaine in range(7):
        OpeningEntry.objects.create(
            weekly_opening=ouverture_hebdomadaire,
            weekday=jour_de_la_semaine,
            start_time=datetime.time(10, 0),
            slot_duration_minutes=60,
            slot_count=8,
        )

    produit = Product.objects.create(
        name=f"{PREFIXE_DE_TEST} ressource {identifiant}",
        categorie_article=Product.RESOURCE,
    )
    tarif = Price.objects.create(
        product=produit,
        name="Tarif horaire",
        prix=Decimal(prix),
        publish=True,
        free_price=prix_libre,
    )
    ressource = Resource.objects.create(
        name=f"{PREFIXE_DE_TEST} ressource {identifiant}",
        product=produit,
        calendar=calendrier,
        weekly_opening=ouverture_hebdomadaire,
        capacity=capacite,
    )

    dans_deux_jours = timezone.localtime(timezone.now()) + timedelta(days=2)
    debut_du_creneau = dans_deux_jours.replace(
        hour=10, minute=0, second=0, microsecond=0
    )

    return SimpleNamespace(
        ressource=ressource,
        produit=produit,
        tarif=tarif,
        debut_du_creneau=debut_du_creneau,
    )


# --------------------------------------------------------------------------
# Ventes déjà faites (état de départ d'un test)
# / Sales already made (a test's starting state)
# --------------------------------------------------------------------------


def creer_un_billet_deja_vendu(acheteur, billetterie):
    """
    Un billet actif déjà vendu à cet acheteur pour cet événement (réservation validée).
    C'est un ÉTAT DE DÉPART fabriqué directement par `create(status=…)`, sans passer par la
    machine à états : il sert à poser une vente antérieure, jamais à tester un paiement
    (tests/PIEGES.md, 9.41 et 12.17).
    / An active ticket already sold: a STARTING STATE built with create(status=...), never
    used to test a payment.
    """
    from BaseBillet.models import PriceSold, ProductSold, Reservation, Ticket

    produit_vendu, _created = ProductSold.objects.get_or_create(
        product=billetterie.produit, event=billetterie.evenement
    )
    tarif_vendu = PriceSold.objects.create(
        productsold=produit_vendu, price=billetterie.tarif, prix=billetterie.tarif.prix
    )
    reservation = Reservation.objects.create(
        user_commande=acheteur, event=billetterie.evenement, status=Reservation.VALID
    )
    Ticket.objects.create(
        reservation=reservation, pricesold=tarif_vendu, status=Ticket.NOT_SCANNED
    )


def creer_un_billet_en_cours_de_paiement(acheteur, billetterie, depuis_minutes):
    """
    Un billet dont le paiement est en cours depuis `depuis_minutes` minutes (réservation non
    payée, billet non actif). ÉTAT DE DÉPART fabriqué par `create(status=…)`. La date de la
    réservation est posée par `update()` : le champ est en `auto_now`.
    / A ticket whose payment has been in progress for `depuis_minutes` minutes.
    """
    from django.utils import timezone
    from BaseBillet.models import PriceSold, ProductSold, Reservation, Ticket

    produit_vendu, _created = ProductSold.objects.get_or_create(
        product=billetterie.produit, event=billetterie.evenement
    )
    tarif_vendu = PriceSold.objects.create(
        productsold=produit_vendu, price=billetterie.tarif, prix=billetterie.tarif.prix
    )
    reservation = Reservation.objects.create(
        user_commande=acheteur, event=billetterie.evenement, status=Reservation.UNPAID
    )
    Ticket.objects.create(
        reservation=reservation, pricesold=tarif_vendu, status=Ticket.NOT_ACTIV
    )
    Reservation.objects.filter(pk=reservation.pk).update(
        datetime=timezone.now() - timedelta(minutes=depuis_minutes)
    )


def creer_une_adhesion_active(utilisateur, adhesion, jours_restants=30):
    """
    Une adhésion payée en base, valable encore `jours_restants` jours (négatif = expirée).
    ÉTAT DE DÉPART fabriqué par `create(status=…)`, comme `creer_un_billet_deja_vendu`.
    / A paid membership in the DB (starting state, built with create(status=...)).
    """
    from django.utils import timezone
    from BaseBillet.models import Membership

    return Membership.objects.create(
        user=utilisateur,
        price=adhesion.tarif,
        status=Membership.ONCE,
        first_name="Ada",
        last_name="Lovelace",
        deadline=timezone.now() + timedelta(days=jours_restants),
    )
