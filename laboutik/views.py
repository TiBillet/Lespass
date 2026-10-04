# laboutik/views.py
# ViewSets DRF pour l'interface de caisse LaBoutik (POS tactile).
# DRF ViewSets for the LaBoutik cash register interface (touch POS).
#
# Authentification : clé API LaBoutik (Discovery / PIN pairing) ou session admin tenant.
# Authentication: LaBoutik API key (Discovery / PIN pairing) or tenant admin session.
#
# CaisseViewSet : données depuis la DB (modèles ORM).
# PaiementViewSet : paiements espèces/CB/NFC depuis la DB (Phase 2 + Phase 3).

import logging
import uuid as uuid_module
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from json import dumps
from types import SimpleNamespace
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import login
from django.db import transaction as db_transaction
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django_htmx.http import HttpResponseClientRedirect
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.db.models import (
    Case,
    Exists,
    IntegerField,
    OuterRef,
    Min,
    Value,
    When,
    Prefetch,
    Sum,
    Count,
    Q,
)

from fedow_core.exceptions import (
    CarteDejaLiee,
    CarteIntrouvable,
    SoldeInsuffisant,
    UserADejaCarte,
)
from fedow_core.models import Asset, Transaction
from fedow_core.services import (
    AssetService,
    CarteService,
    TransactionService,
    WalletService,
)

# Interop reseau federe (FED) : lecture du solde FED sur le serveur Fedow distant.
# / Federated network interop (FED): reads the FED balance from the remote Fedow server.
from fedow_connect.fedow_api import CarteInconnueDeFedow, FedowAPI
from fedow_connect.models import FedowConfig
from fedow_connect.validators import TransactionValidator

from AuthBillet.models import Wallet
from AuthBillet.utils import get_or_create_user
from django.utils import timezone as dj_timezone

from BaseBillet.models import (
    DUREE_D_UN_PAIEMENT_EN_COURS,
    Configuration,
    Event,
    LigneArticle,
    Membership,
    Price,
    PriceSold,
    Product,
    ProductSold,
    SaleOrigin,
    PaymentMethod,
    Ticket,
)
from BaseBillet.models_vente import Reglement, Vente
from BaseBillet.permissions import HasLaBoutikAccess, HasLaBoutikTerminalAccess
from BaseBillet.services_vente import (
    NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE,
    EgaliteDeVenteRompue,
    ajouter_article,
    ajouter_reglement,
    encaisser_vente,
    ouvrir_vente,
    tarif_vendu_d_un_produit_systeme,
)
from QrcodeCashless.models import CarteCashless
# La cloture unique du lieu (la J) et ses lecteurs : exports, presentation, envoi.
# / The venue's single closure (J) and its readers.
from comptabilite.csv_export import generer_csv_cloture
from comptabilite.models import ClotureCaisse as ClotureCaisseUnique
from comptabilite.pdf import generer_pdf_cloture
from comptabilite.presentation import (
    euros_a_la_francaise,
    lignes_du_tiroir,
    montant_a_la_francaise_dans_l_unite,
    sections_pour_affichage,
)
from comptabilite.tasks import (
    creer_la_cloture_journaliere_de_la_caisse,
    demander_l_email_automatique_si_configure,
    envoyer_email_cloture_demande,
)
from laboutik.models import (
    LaboutikConfiguration,
    PointDeVente,
    CartePrimaire,
    Table,
    CommandeSauvegarde,
    ArticleCommandeSauvegarde,
    CorrectionPaiement,
    ImpressionLog,
    SortieCaisse,
    HistoriqueFondDeCaisse,
)
from comptabilite.rapport import (
    MOYENS_CASHLESS,
    RapportDesVentes,
    nom_du_moyen_de_paiement,
)
from laboutik.affichage_des_ventes import (
    articles_de_la_vente_pour_l_affichage,
    badge_de_la_nature_d_une_vente,
    lignes_de_la_liste_des_ventes,
    nom_d_une_monnaie_de_points_introuvable,
    nom_de_l_unite_de_la_vente,
    noms_des_monnaies_des_ventes,
    phrase_d_une_vente_derivee,
    reglements_pour_l_affichage,
)
from laboutik.printing.formatters import formatter_ticket_cloture, formatter_ticket_x
from laboutik.printing.tasks import imprimer_async
from laboutik.serializers import (
    ClientIdentificationSerializer,
    CartePrimaireSerializer,
    PanierSerializer,
    CommandeSerializer,
    ArticleCommandeSerializer,
    ClotureSerializer,
    RechargeMontantLibreSerializer,
)
from laboutik.reports import MOYENS_HORS_ARGENT, RapportComptableService
from inventaire.models import Stock, TypeMouvement
from inventaire.serializers import MouvementRapideSerializer
from inventaire.services import StockService
from wsocket.broadcast import broadcast_stock_update, donnees_badge_stock
from laboutik.integrity import (
    calculer_hmac,
    obtenir_previous_hmac,
    calculer_total_ht,
    vente_couverte_par_cloture,
)


# --------------------------------------------------------------------------- #
#  Constantes                                                                  #
# --------------------------------------------------------------------------- #

# Devise utilisée pour l'affichage des prix
# Currency used for price display
CURRENCY_DATA = {"cc": "EUR", "symbol": "€", "name": "European Euro"}

# Traduction des codes de moyens de paiement pour l'affichage
# Payment method code translations for display
PAYMENT_METHOD_TRANSLATIONS = {
    "nfc": _("cashless"),
    "espece": _("espèce"),
    "carte_bancaire": _("carte bancaire"),
    "CH": _("chèque"),
    "gift": _("cadeau"),
    "": _("inconnu"),
}

# Catégorie par défaut quand un produit n'a pas de categorie_pos
# Default category when a product has no categorie_pos
CATEGORIE_PAR_DEFAUT = {
    "id": "default",
    "name": "Divers",
    "icon": "category",
    "icone_type": "ms",
    "couleur_backgr": "#FFFFFF",
    "couleur_texte": "#333333",
}

# Coupures standard pour la ventilation de sortie de caisse.
# Liste de tuples (valeur_centimes, label_affichage).
# / Standard denominations for cash withdrawal breakdown.
# List of tuples (value_in_cents, display_label).
COUPURES_CENTIMES = [
    (50000, "500 €"),
    (20000, "200 €"),
    (10000, "100 €"),
    (5000, "50 €"),
    (2000, "20 €"),
    (1000, "10 €"),
    (500, "5 €"),
    (200, "2 €"),
    (100, "1 €"),
    (50, "0,50 €"),
    (20, "0,20 €"),
    (10, "0,10 €"),
]

# Version pour le template (liste de dicts pour boucle {% for %})
# / Template-friendly version (list of dicts for {% for %} loop)
_COUPURES_POUR_TEMPLATE = [
    {"centimes": centimes, "label": label, "cle_post": f"coupure_{centimes}"}
    for centimes, label in COUPURES_CENTIMES
]

# Regroupement par paires pour l'affichage en 4 colonnes (2 coupures par ligne).
# Paires adjacentes : (500€, 200€), (100€, 50€), (20€, 10€), (5€, 2€), (1€, 0,50€), (0,20€, 0,10€)
# / Paired grouping for 4-column display (2 denominations per row).
_COUPURES_PAIRES_POUR_TEMPLATE = [
    (_COUPURES_POUR_TEMPLATE[i], _COUPURES_POUR_TEMPLATE[i + 1])
    for i in range(0, len(_COUPURES_POUR_TEMPLATE), 2)
]

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Fonctions utilitaires — état, articles, catégories                         #
#  Utility functions — state, articles, categories                            #
# --------------------------------------------------------------------------- #


def _lire_version():
    """
    Lit le numero de version depuis le fichier VERSION a la racine du projet.
    Format attendu : VERSION=X.Y.Z sur la premiere ligne.
    Retourne la version ou '?' si le fichier est introuvable.
    / Reads the version number from the VERSION file at the project root.
    Expected format: VERSION=X.Y.Z on the first line.
    Returns the version or '?' if the file is not found.

    LOCALISATION : laboutik/views.py
    """
    try:
        chemin_version = settings.BASE_DIR / "VERSION"
        with open(chemin_version, "r") as fichier:
            for ligne in fichier:
                ligne = ligne.strip()
                if ligne.startswith("VERSION="):
                    return ligne.split("=", 1)[1]
    except FileNotFoundError:
        pass
    return "?"


def _construire_state(point_de_vente=None, carte_primaire_obj=None, user=None):
    """
    Construit le dictionnaire "state" à chaque requête.
    Builds the "state" dictionary on each request.

    Le state est lu côté client (JS) via stateJson pour piloter l'interface.
    State is read client-side (JS) via stateJson to drive the interface.

    :param point_de_vente: le PV affiche, si on est sur l'interface caisse
    :param carte_primaire_obj: la carte du responsable de caisse, si elle est posee
    :param user: l'utilisateur de la requete — sert a trouver l'imprimante du terminal
    """
    config = Configuration.get_solo()
    state = {
        "version": _lire_version(),
        "place": {
            "name": config.organisation,
            # Placeholder — sera remplacé par fedow_core en Phase 3
            # Placeholder — will be replaced by fedow_core in Phase 3
            "monnaie_name": "Monnaie locale",
        },
        "demo": {
            "active": getattr(settings, "DEMO", False),
            "tags_id": [
                {"tag_id": settings.DEMO_TAGID_CM, "name": _("Carte primaire")},
                {"tag_id": settings.DEMO_TAGID_CLIENT1, "name": _("Carte client 1")},
                {"tag_id": settings.DEMO_TAGID_CLIENT2, "name": _("Carte client 2")},
                {"tag_id": settings.DEMO_TAGID_CLIENT3, "name": _("Carte client 3")},
                {"tag_id": settings.DEMO_TAGID_CLIENT4, "name": _("Carte inconnue")},
            ],
        },
    }

    # Enrichir avec les propriétés du point de vente (si fourni).
    # Ces champs ne sont pertinents que sur l'interface POS, pas sur la page d'attente.
    # Enrich with point of sale properties (if provided).
    if point_de_vente is not None:
        state["uuid_pv"] = str(point_de_vente.uuid)
        state["comportement"] = point_de_vente.comportement
        state["afficher_les_prix"] = point_de_vente.afficher_les_prix
        state["accepte_especes"] = point_de_vente.accepte_especes
        state["accepte_carte_bancaire"] = point_de_vente.accepte_carte_bancaire
        state["accepte_cheque"] = point_de_vente.accepte_cheque
        state["accepte_commandes"] = point_de_vente.accepte_commandes
        state["service_direct"] = point_de_vente.service_direct
        state["monnaie_principale_name"] = "TestCoin"
        # passageModeGerant : autorise le caissier à basculer en mode gérant
        # passageModeGerant: allows the cashier to switch to manager mode
        state["passageModeGerant"] = True
        state["mode_gerant"] = (
            carte_primaire_obj.edit_mode if carte_primaire_obj else False
        )

    # --- Le canal d'impression de CE terminal ---
    #
    # C'est cette valeur qui dit a la tablette a quel canal WebSocket s'abonner pour
    # recevoir ses tickets : ws/printer/<uuid>/ (laboutik/static/js/manageSunmiPrint.js).
    #
    # ELLE DOIT ETRE PRESENTE SUR TOUTES LES PAGES, y compris l'ecran d'attente de la carte
    # primaire. L'application Android ouvre son WebSocket une seule fois, au demarrage
    # (evenement `deviceready` de Cordova), et la premiere page qu'elle affiche est cet
    # ecran d'attente. Si l'imprimante n'y figurait pas, aucun canal ne serait ouvert, et
    # plus rien ne s'imprimerait de toute la session.
    # / This tells the tablet which WebSocket channel to subscribe to for its tickets.
    # IT MUST BE ON EVERY PAGE, including the primary-card waiting screen: the Android app
    # opens its WebSocket once, at startup (Cordova `deviceready`), and that screen is the
    # first page it shows. Without it, no channel would ever be opened.
    #
    # Vide quand il n'y a rien a imprimer : navigateur d'un gestionnaire (pas un terminal),
    # terminal sans imprimante, ou imprimante desactivee.
    # / Empty when there is nothing to print.
    printer_de_ce_terminal = imprimante_du_terminal(user)
    state["printer"] = {
        # Le PK de Printer s'appelle `uuid`, pas `id`.
        # / Printer's primary key is named `uuid`, not `id`.
        "uuid": str(printer_de_ce_terminal.uuid),
        "name": printer_de_ce_terminal.name,
    } if printer_de_ce_terminal else None

    return state


def _formater_stock_lisible(quantite, unite):
    """
    Formate la quantité de stock en texte lisible pour la tuile POS.
    / Formats the stock quantity as human-readable text for the POS tile.

    Règles / Rules:
      - UN (pièces / units) : "3", "0", "-2"
      - CL (centilitres) : >= 100 → "1.5 L" ou "1 L" ; < 100 → "50 cl"
      - GR (grammes / grams) : >= 1000 → "1.2 kg" ou "1 kg" ; < 1000 → "800 g"
    """
    if unite == "UN":
        return str(quantite)

    if unite == "CL":
        if quantite >= 100:
            litres = quantite / 100
            if litres == int(litres):
                return f"{int(litres)} L"
            return f"{litres:g} L"
        return f"{quantite} cl"

    if unite == "GR":
        if quantite >= 1000:
            kg = quantite / 1000
            if kg == int(kg):
                return f"{int(kg)} kg"
            return f"{kg:g} kg"
        return f"{quantite} g"

    # Fallback — unite inconnue / unknown unit
    return str(quantite)


def _build_stock_context(product, stock, message_feedback=None, erreur_feedback=None):
    """
    Construit le contexte pour le template article_panel_stock.html.
    Convertit les unités de base en unités pratiques pour l'affichage.
    / Builds context for article_panel_stock.html template.
    Converts base units to practical units for display.

    LOCALISATION : laboutik/views.py
    """
    quantite_lisible = _formater_stock_lisible(stock.quantite, stock.unite)
    seuil_lisible = ""
    if stock.seuil_alerte is not None:
        seuil_lisible = _formater_stock_lisible(stock.seuil_alerte, stock.unite)

    # Déterminer l'unité pratique pour le champ de saisie
    # / Determine practical unit for the input field
    unite_saisie_map = {
        "UN": _("pièces"),
        "CL": "cl",
        "GR": "g",
    }
    unite_saisie = unite_saisie_map.get(stock.unite, stock.unite)

    # Déterminer l'état du stock / Determine stock state
    if stock.est_en_rupture():
        etat = "rupture"
    elif stock.est_en_alerte():
        etat = "alerte"
    else:
        etat = "ok"

    # Derniers mouvements manuels (pas les ventes/debits auto)
    # / Recent manual movements (not auto sales/meter debits)
    from inventaire.models import MouvementStock, TypeMouvement as TM

    derniers_mouvements = (
        MouvementStock.objects.filter(stock=stock)
        .exclude(type_mouvement__in=[TM.VE, TM.DM])
        .select_related("cree_par")
        .order_by("-cree_le")[:5]
    )

    return {
        "product": product,
        "stock": stock,
        "quantite_lisible": quantite_lisible,
        "seuil_lisible": seuil_lisible,
        "unite_saisie": unite_saisie,
        "etat": etat,
        "derniers_mouvements": derniers_mouvements,
        "message_feedback": message_feedback,
        "erreur_feedback": erreur_feedback,
    }


def _charger_events_billetterie():
    """
    Charge tous les events futurs avec annotations et prefetch en 3 requêtes max.
    Loads all future events with annotations and prefetch in max 3 queries.

    LOCALISATION : laboutik/views.py

    Retourne (events_list, compteur_tickets_par_price) :
    - events_list : liste d'Event annotés (nb_tickets_valides, nb_en_cours_achat)
      avec produits publiés et prix EUR pré-chargés (to_attr).
    - compteur_tickets_par_price : dict {(event_pk, price_pk): nb_tickets}
      pour les tarifs ayant un stock (jauge par tarif).
    / Returns (events_list, ticket_counts_per_price):
    - events_list: list of annotated Events with prefetched published products + EUR prices.
    - ticket_counts_per_price: dict {(event_pk, price_pk): ticket_count}
      for prices with a stock limit (per-rate gauge).
    """
    now = dj_timezone.now()

    # 1 requête : events annotés avec compteurs tickets
    # / 1 query: events annotated with ticket counters
    events_qs = (
        Event.objects.filter(
            published=True,
            archived=False,
            datetime__gte=now - timedelta(days=1),
        )
        .annotate(
            nb_tickets_valides=Count(
                "reservation__tickets",
                filter=Q(
                    reservation__tickets__status__in=[
                        Ticket.NOT_SCANNED,
                        Ticket.SCANNED,
                    ]
                ),
                distinct=True,
            ),
            nb_en_cours_achat=Count(
                "reservation__tickets",
                filter=Q(
                    reservation__tickets__status__in=[
                        Ticket.CREATED,
                        Ticket.NOT_ACTIV,
                    ],
                    reservation__datetime__gt=now - DUREE_D_UN_PAIEMENT_EN_COURS,
                ),
                distinct=True,
            ),
        )
        .prefetch_related(
            # Prefetch imbriqué : produits publiés → prix EUR publiés
            # / Nested prefetch: published products → published EUR prices
            Prefetch(
                "products",
                queryset=Product.objects.filter(publish=True)
                .select_related("categorie_pos")
                .prefetch_related(
                    Prefetch(
                        "prices",
                        queryset=Price.objects.filter(
                            publish=True, asset__isnull=True
                        ).order_by("order"),
                        to_attr="prix_euros",
                    )
                ),
                to_attr="produits_publies",
            )
        )
        .order_by("datetime")
    )

    # Évaluer le queryset pour pouvoir itérer 2 fois (articles + catégories)
    # / Evaluate queryset so we can iterate twice (articles + categories)
    events_list = list(events_qs)

    # Collecter les (event_pk, price_pk) qui ont un stock (jauge par tarif)
    # / Collect (event_pk, price_pk) pairs that have a stock limit (per-rate gauge)
    event_pks_avec_stock = set()
    price_pks_avec_stock = set()
    for event in events_list:
        for product in event.produits_publies:
            for price in product.prix_euros:
                if price.stock is not None and price.stock > 0:
                    event_pks_avec_stock.add(event.pk)
                    price_pks_avec_stock.add(price.pk)

    # 1 requête batch : compteurs tickets par (event, price) pour les tarifs avec stock
    # / 1 batch query: ticket counts per (event, price) for prices with stock
    compteur_tickets_par_price = {}
    if price_pks_avec_stock:
        rows = (
            Ticket.objects.filter(
                reservation__event__pk__in=event_pks_avec_stock,
                pricesold__price__pk__in=price_pks_avec_stock,
                status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED],
            )
            .values("reservation__event", "pricesold__price")
            .annotate(nb=Count("pk"))
        )
        compteur_tickets_par_price = {
            (row["reservation__event"], row["pricesold__price"]): row["nb"]
            for row in rows
        }

    return events_list, compteur_tickets_par_price


def _tarifs_vendables_a_la_caisse():
    """
    Les tarifs que la caisse sait vendre, les euros d'abord.
    / The prices the POS can sell, euros first.

    LOCALISATION : laboutik/views.py

    - un tarif en euros (sans monnaie) ;
    - OU un tarif en points ou en temps (monnaie FID ou TIM, active, non
      archivee). Les monnaies fiduciaires (TLF, TNF, FED) ne sont jamais un
      prix : elles servent a payer, par la cascade.
    Sans les tarifs faits pour le paiement en ligne (paiement recurrent,
    validation manuelle) : la caisse ne sait pas faire ces parcours.

    Un tarif « en euros » n'a pas de monnaie ET n'est pas coche « non
    fiduciaire » : un tarif coche sans monnaie choisie n'est ni en euros ni en
    points, il n'est pas vendu.

    Les euros d'abord, puis l'ordre d'affichage (entre euros, et entre tarifs en
    points) : le premier tarif sert de tarif par defaut (prix de la tuile,
    ancien format de panier sans price_uuid).

    Appelee par / Called by : _construire_donnees_articles(),
    _extraire_articles_du_panier().
    """
    tarif_en_euros = Q(asset__isnull=True, non_fiduciaire=False)
    tarif_en_points_ou_en_temps = Q(
        non_fiduciaire=True,
        asset__category__in=[Asset.TIM, Asset.FID],
        asset__active=True,
        asset__archive=False,
    )
    return (
        Price.objects.filter(
            tarif_en_euros | tarif_en_points_ou_en_temps,
            publish=True,
            recurring_payment=False,
            manual_validation=False,
        )
        .select_related("asset")
        .annotate(
            # 0 pour un tarif en euros, 1 pour un tarif en points : les euros
            # passent devant, puis `order` departage, quelle que soit la monnaie.
            # / 0 for euros, 1 for points: euros first, then `order`.
            rang_de_la_monnaie=Case(
                When(asset__isnull=True, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("rang_de_la_monnaie", "order")
    )


def _unite_du_tarif(tarif):
    """
    L'unite a afficher a cote du prix d'un tarif : le nom de sa monnaie
    (« Points fidélité », « Temps ») pour un tarif en points ou en temps, le
    symbole € sinon.
    / The unit shown next to a price: currency name for points/time, € otherwise.

    LOCALISATION : laboutik/views.py

    :param tarif: Price (avec son asset charge par select_related)
    :return: str
    """
    if not _tarif_est_en_points(tarif):
        return CURRENCY_DATA["symbol"]
    if tarif.asset_id is None:
        return str(_("Points ou temps"))
    return tarif.asset.name


def _initiales_de_la_monnaie(nom_de_la_monnaie):
    """
    Les initiales d'un nom de monnaie, pour la place reduite d'une tuile :
    « Points fidélité » → « PF », « Temps » → « T ».
    Deux monnaies peuvent avoir les memes initiales (« Points fidélité »,
    « Points festival ») : la tuile porte le nom complet en infobulle (<abbr>).
    / Initials of a currency name, for the small space of a tile. The full name
      is the tile tooltip.

    LOCALISATION : laboutik/views.py

    :param nom_de_la_monnaie: str
    :return: str
    """
    initiales = ""
    for mot in nom_de_la_monnaie.split():
        initiales += mot[0].upper()
    return initiales


def _retirer_les_tarifs_en_points_non_vendables(produit):
    """
    Un tarif en points ne se vend que sur un article de vente ou une adhesion :
    sur tout autre produit (recharge, consigne...), on le retire de
    `produit.prix_euros`. L'admin refuse ce cas ; la caisse le refuse aussi,
    pour un tarif ecrit en base par un autre chemin (API, script).
    / A points price only sells on a sale item or a membership: removed otherwise.

    LOCALISATION : laboutik/views.py

    :param produit: Product dont `prix_euros` vient de _tarifs_vendables_a_la_caisse()
    """
    produit_est_une_vente = produit.methode_caisse == Product.VENTE
    produit_est_une_adhesion = produit.categorie_article == Product.ADHESION
    if produit_est_une_vente or produit_est_une_adhesion:
        return

    tarifs_en_euros_seulement = []
    for tarif in produit.prix_euros:
        if not _tarif_est_en_points(tarif):
            tarifs_en_euros_seulement.append(tarif)
    produit.prix_euros = tarifs_en_euros_seulement


def _construire_donnees_articles(point_de_vente_instance, events_billetterie=None):
    """
    Construit la liste de dicts articles au format attendu par les templates.
    Builds the list of article dicts in the format expected by templates.

    LOCALISATION : laboutik/views.py

    Chaque produit doit avoir au moins un tarif vendable a la caisse (voir
    _tarifs_vendables_a_la_caisse). Les produits sans tarif sont ignorés.
    Each product must have at least one POS-sellable price. Products without a
    price are skipped.

    """
    # Prefetch filtré : les tarifs vendables a la caisse, les euros d'abord.
    # Le .filter() dans la boucle utiliserait une nouvelle requête par produit (N+1).
    # Avec Prefetch(queryset=...), Django charge tout en 1 requête et filtre en mémoire.
    # L'attribut garde le nom « prix_euros » : il contient aussi les tarifs en
    # points ou en temps, mais toujours APRES les tarifs en euros.
    # / Filtered prefetch: POS-sellable prices, euros first. The attribute keeps
    #   the name "prix_euros": it also holds points/time prices, after the euros.
    prix_euros_prefetch = Prefetch(
        "prices",
        queryset=_tarifs_vendables_a_la_caisse(),
        to_attr="prix_euros",
    )

    # Produits du M2M du PV : articles POS (methode_caisse) OU adhesions (categorie_article)
    # Les adhesions n'ont pas forcement de methode_caisse, elles sont identifiees par categorie_article.
    # / POS M2M products: POS articles (methode_caisse) OR memberships (categorie_article)
    # Memberships don't necessarily have methode_caisse, identified by categorie_article.
    produits = list(
        point_de_vente_instance.products.filter(
            Q(methode_caisse__isnull=False) | Q(categorie_article=Product.ADHESION)
        )
        .select_related("categorie_pos", "stock_inventaire", "asset")
        .prefetch_related(prix_euros_prefetch)
        .order_by("poids", "name")
    )

    articles = []
    for product in produits:
        # Recharge temps desactivee : ne jamais afficher un produit TM.
        # Il n'est plus dans METHODES_RECHARGE, donc sans ce filtre il
        # s'afficherait comme un article normal, paye en euros.
        # / Time top-up disabled: never show a TM product (it would look like
        # a normal paid item since it is no longer in METHODES_RECHARGE).
        if product.methode_caisse == Product.RECHARGE_TEMPS:
            continue

        # Produits de recharge sans Asset lie, ou Asset archive/inactif → ne pas afficher
        # / Top-up products without linked Asset, or archived/inactive Asset → skip
        if product.methode_caisse in METHODES_RECHARGE:
            if (
                product.asset is None
                or product.asset.archive
                or not product.asset.active
            ):
                continue

        _retirer_les_tarifs_en_points_non_vendables(product)

        # Premier tarif : un tarif en euros s'il y en a un (tri du Prefetch)
        # / First price: a euro price if there is one (Prefetch ordering)
        if not product.prix_euros:
            continue
        prix_obj = product.prix_euros[0]

        prix_en_centimes = int(round(prix_obj.prix * 100))

        # Un retour de consigne affiche le prix du gobelet qu'il rembourse, jamais le
        # sien : la tuile doit annoncer ce que la caisse rendra vraiment.
        # Quand la caisse ne sait pas calculer ce prix (pas de consigne reliée, ou
        # gobelet sans tarif en euros vendable), le retour n'a PAS de tuile. La vente
        # reste refusée en plus, si un panier l'envoie quand même
        # (_extraire_articles_du_panier).
        # / A deposit return shows the cup's price, never its own. When that price
        #   cannot be computed, the return has NO tile.
        prix_de_la_consigne_remboursee_en_centimes = None
        if product.methode_caisse == Product.RETOUR_CONSIGNE:
            try:
                prix_de_la_consigne_remboursee_en_centimes = (
                    _prix_de_la_consigne_remboursee_en_centimes(product)
                )
            except ValueError:
                continue
        if prix_de_la_consigne_remboursee_en_centimes is not None:
            prix_en_centimes = prix_de_la_consigne_remboursee_en_centimes

        # Catégorie POS du produit (ou catégorie par défaut)
        # Product POS category (or default category)
        categorie_pos = product.categorie_pos
        if categorie_pos is not None:
            # Nom d'icone Material Symbols (selecteur de l'admin : ICON_POS)
            # / Material Symbols icon name (admin picker: ICON_POS)
            icone_cat_brute = categorie_pos.icon or ""
            icone_type_cat = "ms" if icone_cat_brute else ""
            categorie_dict = {
                "id": str(categorie_pos.uuid),
                "name": categorie_pos.name,
                "icon": icone_cat_brute,
                "icone_type": icone_type_cat,
                "couleur_backgr": categorie_pos.couleur_fond or "#17a2b8",
                "couleur_texte": categorie_pos.couleur_texte,
            }
        else:
            categorie_dict = CATEGORIE_PAR_DEFAUT

        # Image du produit (thumbnail med)
        # Product image (med thumbnail)
        url_image = None
        if product.img:
            try:
                url_image = product.img.med.url
            except Exception:
                url_image = None

        # Multi-tarif : le produit a plusieurs prix OU un prix libre.
        # On inclut tous les tarifs dans les data pour le JS côté client.
        # Multi-rate: product has multiple prices OR a free price.
        # Include all rates in data for client-side JS.
        est_adhesion = product.categorie_article == Product.ADHESION
        a_prix_libre = any(p.free_price for p in product.prix_euros)
        # Poids/mesure : au moins un tarif nécessite la saisie d'une quantité (vente au poids/volume).
        # On force l'ouverture de l'overlay (multi_tarif=True) même si un seul tarif.
        # / Weight-based: at least one price requires quantity input (sold by weight/volume).
        # Force overlay opening (multi_tarif=True) even with a single price.
        a_poids_mesure = any(p.poids_mesure for p in product.prix_euros)
        multi_tarif = len(product.prix_euros) > 1 or a_prix_libre or a_poids_mesure

        tarifs = []
        if multi_tarif:
            for p in product.prix_euros:
                # Un retour de consigne relié : chaque tarif rend le prix du gobelet.
                # / A linked deposit return: every price gives back the cup's price.
                if prix_de_la_consigne_remboursee_en_centimes is not None:
                    prix_du_tarif_en_centimes = prix_de_la_consigne_remboursee_en_centimes
                else:
                    prix_du_tarif_en_centimes = int(round(p.prix * 100))
                tarifs.append(
                    {
                        "price_uuid": str(p.uuid),
                        "name": p.name,
                        "prix_centimes": prix_du_tarif_en_centimes,
                        # Unite du prix (tuile, popup des tarifs, panier)
                        # / Price unit (tile, rate popup, cart)
                        "unite_label": _unite_du_tarif(p),
                        # Tuile : les initiales de la monnaie (place reduite)
                        # / Tile: the currency initials (small space)
                        "unite_courte": _initiales_de_la_monnaie(_unite_du_tarif(p)),
                        "est_en_points": _tarif_est_en_points(p),
                        "free_price": p.free_price,
                        "poids_mesure": p.poids_mesure,
                        # Quantite de stock retiree par unite vendue (ex : 50 cl).
                        # Lue par la garde stock au clic (articles.js).
                        # / Stock quantity removed per unit sold. Read by the click stock guard.
                        "contenance": p.contenance or 1,
                        "unite_saisie_label": "",  # sera enrichi ci-dessous / will be enriched below
                        "prix_reference_label": "",  # sera enrichi ci-dessous / will be enriched below
                        "subscription_label": p.get_subscription_type_display()
                        if hasattr(p, "get_subscription_type_display")
                        else "",
                    }
                )

        # --- Enrichissement poids/mesure : unités de saisie et labels de prix de référence ---
        # Déterminé à partir du Stock lié (unite GR → grammes/kg, CL → centilitres/litres).
        # On enrichit aussi les tarifs avec stock_disponible et autoriser_hors_stock
        # pour la garde JS au pave numerique (bug 8).
        # / Weight-based enrichment: input units and reference price labels.
        # We also enrich the tariffs with stock_disponible and autoriser_hors_stock
        # for the JS guard on the numpad (bug 8).
        unite_saisie_label = "g"
        prix_reference_label = "/kg"
        stock_disponible_pm = None
        autoriser_hors_stock_pm = True
        if a_poids_mesure:
            try:
                stock_du_produit_pm = product.stock_inventaire
                stock_disponible_pm = stock_du_produit_pm.quantite
                autoriser_hors_stock_pm = stock_du_produit_pm.autoriser_vente_hors_stock
                if stock_du_produit_pm.unite == "GR":
                    unite_saisie_label = "g"
                    prix_reference_label = "/kg"
                elif stock_du_produit_pm.unite == "CL":
                    unite_saisie_label = "cl"
                    prix_reference_label = "/L"
                else:
                    unite_saisie_label = "g"
                    prix_reference_label = "/kg"
            except Exception:
                # Pas de stock (ne devrait pas arriver, save_related en crée un)
                # / No stock (should not happen, save_related creates one)
                unite_saisie_label = "g"
                prix_reference_label = "/kg"
            # Enrichir les tarifs poids_mesure avec l'unité de saisie + stock
            # / Enrich weight-based prices with input unit + stock
            for t in tarifs:
                if t.get("poids_mesure"):
                    t["unite_saisie_label"] = unite_saisie_label
                    t["prix_reference_label"] = prix_reference_label
                    t["stock_disponible"] = stock_disponible_pm
                    t["autoriser_hors_stock"] = autoriser_hors_stock_pm

        # Couleurs : override produit si défini, sinon catégorie
        # Colors: product override if set, otherwise category
        couleur_backgr = product.couleur_fond_pos or (
            categorie_pos.couleur_fond if categorie_pos else "#17a2b8"
        )
        couleur_texte_article = product.couleur_texte_pos or (
            categorie_pos.couleur_texte if categorie_pos else "#333333"
        )

        # Icône : override produit si défini, sinon icône de la catégorie, sinon rien
        # Icon: product override if set, otherwise category icon, otherwise nothing
        icone_brute = (
            product.icon_pos or (categorie_pos.icon if categorie_pos else None) or ""
        )

        # Nom d'icone Material Symbols, affiche tel quel par la caisse
        # / Material Symbols icon name, shown as-is by the POS
        icone_article = icone_brute
        icone_type = "ms" if icone_article else ""

        article_dict = {
            "id": str(product.uuid),
            "name": product.name,
            "prix": prix_en_centimes,
            "categorie": categorie_dict,
            # Contenance du tarif principal : stock retire par clic sur la tuile
            # (articles mono-tarif). Lue par la garde stock (articles.js).
            # / Main price contenance: stock removed per tile click. Read by the stock guard.
            "contenance": prix_obj.contenance or 1,
            # Unite du prix de la tuile : celle du premier tarif (les euros d'abord)
            # / Tile price unit: the first price's (euros first)
            "unite_label": _unite_du_tarif(prix_obj),
            "unite_courte": _initiales_de_la_monnaie(_unite_du_tarif(prix_obj)),
            "est_en_points": _tarif_est_en_points(prix_obj),
            "couleur_backgr": couleur_backgr,
            "couleur_texte": couleur_texte_article,
            "icone": icone_article,
            "icone_type": icone_type,  # "ms" | ""
            "bt_groupement": {
                # Groupement automatique par méthode de caisse — plus de champ groupe_pos
                # Automatic grouping by POS method — no more groupe_pos field
                "groupe": f"groupe_{product.methode_caisse or ('AD' if est_adhesion else 'VT')}",
            },
            "url_image": url_image,
            "est_adhesion": est_adhesion,
            "multi_tarif": multi_tarif,
            "a_prix_libre": a_prix_libre,
            "a_poids_mesure": a_poids_mesure,
            "unite_saisie_label": unite_saisie_label if a_poids_mesure else "",
            "prix_reference_label": prix_reference_label if a_poids_mesure else "",
            "tarifs": tarifs,
            "tarifs_json": dumps(tarifs) if tarifs else "[]",
            "methode_caisse": product.methode_caisse or "",
            # RC (cadeau) et TM (temps) : pas de symbole € sur le prix,
            # car ce ne sont pas des euros mais des unites de monnaie cadeau/temps.
            # / RC (gift) and TM (time): no € symbol on the price,
            # because they are not euros but gift/time currency units.
            "est_recharge_gratuite": product.methode_caisse
            in METHODES_RECHARGE_GRATUITES,
        }

        # --- Données stock pour l'affichage dans la tuile POS ---
        # Si le produit a un Stock lié, on enrichit le dict avec l'état du stock.
        # Sinon, stock_quantite=None signifie "pas de gestion de stock".
        # / If the product has a linked Stock, enrich the dict with stock state.
        # Otherwise, stock_quantite=None means "no stock management".
        try:
            stock_du_produit = product.stock_inventaire
            est_en_rupture = stock_du_produit.est_en_rupture()
            article_dict["stock_quantite"] = stock_du_produit.quantite
            article_dict["stock_unite"] = stock_du_produit.unite
            article_dict["stock_en_alerte"] = stock_du_produit.est_en_alerte()
            article_dict["stock_en_rupture"] = est_en_rupture
            article_dict["stock_bloquant"] = (
                est_en_rupture and not stock_du_produit.autoriser_vente_hors_stock
            )
            article_dict["stock_autoriser_hors_stock"] = (
                stock_du_produit.autoriser_vente_hors_stock
            )
            article_dict["stock_quantite_lisible"] = _formater_stock_lisible(
                stock_du_produit.quantite, stock_du_produit.unite
            )
        except Stock.DoesNotExist:
            article_dict["stock_quantite"] = None

        articles.append(article_dict)

    # --- PV BILLETTERIE : construire les articles depuis les événements futurs ---
    # Chaque event → chaque Product lié → chaque Price publiée EUR = 1 tuile.
    # Jauge sur la tuile : Price.stock si défini, sinon Event.jauge_max.
    # Les articles du M2M (ci-dessus) sont déjà dans la liste.
    # / BILLETTERIE POS: build articles from future events.
    # Each event → each linked Product → each published EUR Price = 1 tile.
    # Gauge on tile: Price.stock if set, otherwise Event.jauge_max.
    # M2M articles (above) are already in the list.
    est_pv_billetterie = (
        point_de_vente_instance.comportement == PointDeVente.BILLETTERIE
    )
    if est_pv_billetterie and events_billetterie is not None:
        events_list, compteur_tickets_par_price = events_billetterie

        # Palette de couleurs pour distinguer les events visuellement
        # Chaque event reçoit une couleur de fond unique.
        # / Color palette to visually distinguish events.
        # Each event gets a unique background color.
        couleurs_events = [
            "#7C3AED",  # violet
            "#2563EB",  # bleu
            "#059669",  # vert emeraude
            "#D97706",  # ambre
            "#DC2626",  # rouge
            "#7C3AED",  # violet (cycle)
            "#0891B2",  # cyan
            "#BE185D",  # rose
        ]

        for index_event, event in enumerate(events_list):
            # Compteurs pré-calculés par annotation (0 requête)
            # / Pre-computed counters via annotation (0 queries)
            places_vendues_event = event.nb_tickets_valides
            jauge_max_event = event.jauge_max or 0
            est_complet_event = (
                jauge_max_event > 0
                and (places_vendues_event + event.nb_en_cours_achat) >= jauge_max_event
            )

            # Couleur de fond par event (palette cyclique)
            # / Background color per event (cyclic palette)
            couleur_fond_event = couleurs_events[index_event % len(couleurs_events)]

            # Produits publiés pré-chargés par Prefetch (to_attr, 0 requête)
            # / Published products pre-loaded by Prefetch (to_attr, 0 queries)
            produits_event = event.produits_publies
            if not produits_event:
                continue

            for product in produits_event:
                # Couleurs : couleur event par défaut, override par le produit si défini
                # / Colors: event color by default, product override if set
                categorie_pos = product.categorie_pos
                couleur_fond = product.couleur_fond_pos or couleur_fond_event
                couleur_texte = (
                    product.couleur_texte_pos
                    or (categorie_pos.couleur_texte if categorie_pos else None)
                    or "#ffffff"
                )
                # Icone Material (defaut : un billet) / Material icon (default: a ticket)
                icone_brute = (
                    product.icon_pos
                    or (categorie_pos.icon if categorie_pos else None)
                    or "confirmation_number"
                )
                icone_type = "ms"

                # Image du produit
                # / Product image
                url_image = None
                if product.img:
                    try:
                        url_image = product.img.med.url
                    except Exception:
                        url_image = None

                # Prix EUR pré-chargés par Prefetch (to_attr, 0 requête)
                # / EUR prices pre-loaded by Prefetch (to_attr, 0 queries)
                for price in product.prix_euros:
                    prix_en_centimes = int(round(price.prix * 100))

                    # Jauge : Price.stock si défini, sinon Event.jauge_max
                    # / Gauge: Price.stock if set, otherwise Event.jauge_max
                    if price.stock is not None and price.stock > 0:
                        # Jauge par tarif — lookup dans le dict batch (0 requête)
                        # / Per-rate gauge — lookup in batch dict (0 queries)
                        places_vendues_tuile = compteur_tickets_par_price.get(
                            (event.pk, price.pk), 0
                        )
                        jauge_max_tuile = price.stock
                        est_complet_tuile = places_vendues_tuile >= price.stock
                    else:
                        # Jauge globale de l'event
                        # / Global event gauge
                        jauge_max_tuile = jauge_max_event
                        places_vendues_tuile = places_vendues_event
                        est_complet_tuile = est_complet_event

                    pourcentage_tuile = (
                        int(round(places_vendues_tuile / jauge_max_tuile * 100))
                        if jauge_max_tuile
                        else 0
                    )

                    article_billet = {
                        # ID composite event__price : identifie sans ambiguïté
                        # quel tarif (Price) de quel événement (Event) le client a choisi.
                        # Le séparateur '__' ne conflicte pas avec '--' (multi-tarif).
                        # Le JS traite data-uuid comme une string opaque.
                        # / Composite event__price ID: unambiguously identifies
                        # which rate (Price) of which event (Event) the client chose.
                        "id": f"{event.uuid}__{price.uuid}",
                        "name": price.name or product.name,
                        "prix": prix_en_centimes,
                        # La catégorie utilise l'UUID de l'event pour le filtre sidebar
                        # / Category uses event UUID for sidebar filter
                        "categorie": {
                            "id": str(event.uuid),
                            "name": event.name,
                            "icon": "calendar_month",
                            "icone_type": "ms",
                            "couleur_backgr": couleur_fond,
                            "couleur_texte": couleur_texte,
                        },
                        "couleur_backgr": couleur_fond,
                        "couleur_texte": couleur_texte,
                        "icone": icone_brute,
                        "icone_type": icone_type,
                        "bt_groupement": {"groupe": "groupe_BI"},
                        "url_image": url_image,
                        "est_adhesion": False,
                        "multi_tarif": False,
                        "a_prix_libre": price.free_price,
                        "tarifs": [],
                        "tarifs_json": "[]",
                        "methode_caisse": "BI",
                        "event": {
                            "uuid": str(event.uuid),
                            "name": event.name,
                            "datetime": event.datetime,
                            "jauge_max": jauge_max_tuile,
                            "places_vendues": places_vendues_tuile,
                            "places_restantes": max(
                                0, jauge_max_tuile - places_vendues_tuile
                            )
                            if jauge_max_tuile
                            else None,
                            "pourcentage": pourcentage_tuile,
                            "complet": est_complet_tuile,
                        },
                    }
                    articles.append(article_billet)

    return articles


def _construire_donnees_categories(point_de_vente_instance, events_billetterie=None):
    """
    Construit la liste de dicts catégories au format attendu par les templates.
    Pour un PV BILLETTERIE, ajoute les events futurs comme pseudo-catégories
    avec date et mini-jauge (filtre CSS cat-{event_uuid}).
    / Builds the list of category dicts in the format expected by templates.
    For a BILLETTERIE POS, adds future events as pseudo-categories
    with date and mini-gauge (CSS filter cat-{event_uuid}).

    LOCALISATION : laboutik/views.py
    """
    # Catégories classiques du M2M (Bar, etc.) — toujours chargées
    # / Classic M2M categories (Bar, etc.) — always loaded
    categories_qs = point_de_vente_instance.categories.order_by("poid_liste", "name")
    categories = []
    for categorie in categories_qs:
        # Icone Material (defaut : grille) / Material icon (default: grid)
        icone_cat = categorie.icon or "apps"
        icone_type_cat = "ms"
        categories.append(
            {
                "id": str(categorie.uuid),
                "name": categorie.name,
                "icon": icone_cat,
                "icone_type": icone_type_cat,
            }
        )

    # PV BILLETTERIE : ajouter les events futurs comme pseudo-catégories
    # La jauge event dans la sidebar = jauge globale (toutes catégories confondues)
    # / BILLETTERIE POS: add future events as pseudo-categories
    # Event gauge in sidebar = global gauge (all rates combined)
    est_pv_billetterie = (
        point_de_vente_instance.comportement == PointDeVente.BILLETTERIE
    )
    if est_pv_billetterie and events_billetterie is not None:
        events_list, _compteur = events_billetterie

        for event in events_list:
            # Ignorer les events sans produit publié (déjà filtré par Prefetch)
            # / Skip events without published products (already filtered by Prefetch)
            if not event.produits_publies:
                continue

            places_vendues = event.nb_tickets_valides
            jauge_max = event.jauge_max or 0
            pourcentage = (
                int(round(places_vendues / jauge_max * 100)) if jauge_max else 0
            )
            est_complet = (
                jauge_max > 0
                and (places_vendues + event.nb_en_cours_achat) >= jauge_max
            )
            categories.append(
                {
                    "id": str(event.uuid),
                    "name": event.name,
                    "icon": "calendar_month",
                    "icone_type": "ms",
                    "is_event": True,
                    "date": event.datetime,
                    "jauge_max": jauge_max,
                    "places_vendues": places_vendues,
                    "pourcentage": pourcentage,
                    "complet": est_complet,
                }
            )

    return categories


def _charger_carte_primaire(tag_id):
    """
    Cherche une carte primaire à partir d'un tag NFC.
    Retourne (carte_primaire_obj, erreur_str). Si erreur_str n'est pas None, la carte n'a pas été trouvée.
    / Looks up a primary card from an NFC tag. Returns (primary_card_obj, error_str).
    """
    try:
        carte_cashless = CarteCashless.objects.get(tag_id=tag_id)
    except CarteCashless.DoesNotExist:
        return None, _("Carte inconnue")

    try:
        carte_primaire_obj = CartePrimaire.objects.get(carte=carte_cashless)
    except CartePrimaire.DoesNotExist:
        return None, _("Carte non primaire")

    return carte_primaire_obj, None


def _verifier_carte_primaire_aupres_de_l_ancien_fedow(carte_primaire_obj):
    """
    Demande à l'ancien Fedow si la carte est encore une carte primaire de ce lieu.
    Retourne None si oui, sinon le message d'erreur à afficher.
    / Asks the old Fedow whether the card is still a primary card of this venue.
    Returns None if so, otherwise the error message to display.

    LOCALISATION : laboutik/views.py

    Appelée par CaisseViewSet.carte_primaire(), à l'ouverture de la caisse, une fois la
    carte primaire trouvée en local. Même comportement que LaBoutik V1
    (../LaBoutik/webview/views.py) : l'ancien Fedow fait autorité. Il peut retirer une
    carte primaire sans prévenir la caisse (VOID de la carte, carte perdue).
    L'ancien Fedow calcule `is_primary` pour le lieu qui signe la requête.

    FLUX :
    1. Lieu non relié à l'ancien Fedow : ouverture refusée, rien n'est supprimé.
    2. On lit la carte sur l'ancien Fedow (`NFCcard.retrieve`). Serveur injoignable,
       erreur HTTP, réponse illisible ou carte inconnue : ouverture refusée, rien
       n'est supprimé.
    3. `is_primary` faux : la carte primaire locale est supprimée, ouverture refusée.
       Suppression locale seulement : l'ancien Fedow ne la connaît déjà plus comme
       carte primaire, on ne lui renvoie rien.
    4. `is_primary` vrai : None, la caisse s'ouvre.

    :param carte_primaire_obj: CartePrimaire trouvée en local
    :return: None si la carte est confirmée, sinon le message d'erreur (str)
    """
    tag_id_de_la_carte = carte_primaire_obj.carte.tag_id

    # Garde indispensable : on teste can_fedow() AVANT de créer FedowAPI. Sur un lieu
    # sans place Fedow, sa création lancerait create_place() (un appel réseau).
    # / Mandatory guard: check can_fedow() BEFORE building FedowAPI.
    lieu_relie_a_l_ancien_fedow = FedowConfig.get_solo().can_fedow()
    if not lieu_relie_a_l_ancien_fedow:
        logger.error(
            f"carte_primaire : ouverture refusée pour la carte {tag_id_de_la_carte}, "
            f"le lieu n'est pas relié à l'ancien Fedow."
        )
        return _("Ce lieu n'est pas relié à Fedow : prévenez un responsable.")

    # Toute erreur de lecture refuse l'ouverture sans rien supprimer : on ne sait pas
    # si la carte est encore primaire. Le message est le même pour toutes les causes,
    # la cause réelle part dans le journal.
    # / Any read error refuses the opening without deleting anything.
    message_verification_impossible = _(
        "Impossible de vérifier la carte primaire auprès de Fedow. "
        "Réessayez dans un instant, puis prévenez un responsable si cela recommence."
    )
    try:
        fiche_de_la_carte = FedowAPI().NFCcard.retrieve(tag_id_de_la_carte)
    # Branche séparée pour un journal plus clair : le gérant lit « carte inconnue ».
    # / Separate branch for a clearer log: the manager reads "unknown card".
    except CarteInconnueDeFedow as erreur_carte_inconnue:
        logger.error(
            f"carte_primaire : ouverture refusée, carte {tag_id_de_la_carte} "
            f"inconnue de l'ancien Fedow : {erreur_carte_inconnue}"
        )
        return message_verification_impossible
    except Exception as erreur_de_l_ancien_fedow:
        logger.error(
            f"carte_primaire : ouverture refusée, lecture de la carte "
            f"{tag_id_de_la_carte} sur l'ancien Fedow en échec : "
            f"{type(erreur_de_l_ancien_fedow).__name__} {erreur_de_l_ancien_fedow}"
        )
        return message_verification_impossible

    carte_encore_primaire = fiche_de_la_carte["is_primary"]
    if not carte_encore_primaire:
        logger.warning(
            f"carte_primaire : la carte {tag_id_de_la_carte} n'est plus primaire pour "
            f"ce lieu sur l'ancien Fedow. Carte primaire locale supprimée."
        )
        carte_primaire_obj.delete()
        return _(
            "Cette carte n'est plus une carte primaire pour ce lieu. "
            "Prévenez un responsable."
        )

    return None


def _carte_primaire_a_un_point_de_vente_cashless(tag_id_carte_primaire):
    """
    La carte primaire du caissier donne-t-elle acces a un point de vente cashless ?
    / Does the cashier's primary card give access to a cashless POS?

    LOCALISATION : laboutik/views.py

    Regle metier : la zone « Recharger » de la popup check carte ne s'affiche
    que si la carte primaire a au moins un point de vente CASHLESS.
    Un caissier de bar sans PV cashless ne voit donc pas la recharge.
    Sans carte primaire (acces admin par session), pas de recharge non plus.
    / Business rule: the check card "Top up" zone only shows when the primary
    card has at least one CASHLESS POS. No primary card: no top-up either.

    Utilise par / Used by : PaiementViewSet.retour_carte()

    :param tag_id_carte_primaire: tag_id de la carte primaire (str, peut etre vide)
    :return: bool
    """
    if not tag_id_carte_primaire:
        return False

    carte_primaire_obj, erreur = _charger_carte_primaire(tag_id_carte_primaire)
    if erreur is not None:
        return False

    return carte_primaire_obj.points_de_vente.filter(
        comportement=PointDeVente.CASHLESS,
    ).exists()


def obtenir_wallet_carte_depuis_fedow(carte):
    """
    Demande a Fedow (source de verite) le wallet de la carte et le miroir en
    local avec le MEME uuid. C'est le seul moyen d'avoir un wallet capable de
    recevoir du FED (qui vit dans Fedow), exactement comme le fait LaBoutik V1.
    / Asks Fedow (source of truth) for the card's wallet and mirrors it locally
    with the SAME uuid — the only way to hold FED (which lives in Fedow).

    LOCALISATION : laboutik/views.py

    POINT DE DEBRANCHEMENT : le jour ou le Fedow legacy sera debranche, on
    remplacera UNIQUEMENT le corps de cette fonction par une creation interne
    (fedow_core), sans toucher au reste du POS.
    / DEBRANCH POINT: when legacy Fedow is removed, replace ONLY this body with
    an internal (fedow_core) wallet creation.

    Retourne le Wallet (uuid Fedow) ou None si Fedow ne connait pas la carte.
    On ne fabrique PAS la carte au scan (comme V1) : le provisioning des cartes
    se fait en amont (seed / import).
    / Returns the Wallet (Fedow uuid) or None if Fedow doesn't know the card.

    EFFET DE BORD : si Fedow signale une carte anonyme (wallet ephemere) et que la
    carte locale n'a pas encore d'user, la fonction RATTACHE le wallet a la carte
    (carte.save(update_fields=["wallet_ephemere"])). Sinon, aucune ecriture.
    / SIDE EFFECT: for an anonymous card (ephemeral wallet) with no user yet, attaches
    the wallet to the local card via carte.save(). Otherwise no write.

    :param carte: CarteCashless
    :return: Wallet | None
    """
    # Garde indispensable : on teste can_fedow() AVANT d'instancier FedowAPI.
    # Sinon, sur un tenant sans place Fedow configurée, l'instanciation de
    # PlaceFedow déclenche create_place() (handshake réseau involontaire) à
    # chaque scan. Sans Fedow, le wallet ne peut pas être résolu : on retourne
    # None et l'appelant lèvera son exception "carte inconnue de Fedow".
    # / Mandatory guard: check can_fedow() BEFORE instantiating FedowAPI. Otherwise,
    # on a tenant with no Fedow place, instantiating PlaceFedow triggers create_place()
    # (an unwanted network handshake) on every scan. Without Fedow the wallet cannot be
    # resolved: return None and let the caller raise its "card unknown to Fedow" error.
    if not FedowConfig.get_solo().can_fedow():
        return None

    # On demande a Fedow le wallet de la carte (par son tag_id physique).
    # / Ask Fedow for the card's wallet (by its physical tag_id).
    serialized = FedowAPI().NFCcard.card_tag_id_retrieve(carte.tag_id)
    if serialized is None:
        # Fedow ne connait pas la carte (404) ou est indisponible : on ne cree
        # PAS de wallet local, sinon on creerait un doublon deconnecte de Fedow.
        # / Fedow doesn't know the card / is down: do NOT create a local wallet.
        logger.warning(
            f"obtenir_wallet_carte_depuis_fedow : carte {carte.tag_id} inconnue de Fedow"
        )
        return None

    # Miroir local du wallet Fedow, avec le MEME uuid (Fedow fait foi).
    # / Local mirror of the Fedow wallet, with the SAME uuid (Fedow is the source).
    wallet, _cree = Wallet.objects.get_or_create(
        uuid=serialized["wallet_uuid"],
        defaults={
            "origin": connection.tenant,
            "name": f"Wallet carte {carte.tag_id}",
        },
    )

    # Carte anonyme cote Fedow (wallet ephemere, pas encore d'user) : on rattache
    # ce wallet a la carte locale pour les prochains scans.
    # / Anonymous card on Fedow side: attach this wallet to the local card.
    if serialized["is_wallet_ephemere"] and not carte.user:
        carte.wallet_ephemere = wallet
        carte.save(update_fields=["wallet_ephemere"])

    return wallet


def _obtenir_ou_creer_wallet(carte):
    """
    Retourne le wallet associé à une CarteCashless.
    Returns the wallet associated with a CarteCashless.

    LOCALISATION : laboutik/views.py

    Priorité / Priority :
    1. carte.user.wallet (si user et wallet existent)
    2. carte.wallet_ephemere (si existe)
    3. Créer un wallet éphémère et l'attacher à la carte

    :param carte: CarteCashless
    :return: Wallet
    """
    # 1. Carte liée à un user qui a déjà un wallet
    # 1. Card linked to a user who already has a wallet
    if carte.user and carte.user.wallet:
        return carte.user.wallet

    # 2. Carte anonyme avec wallet éphémère existant
    # 2. Anonymous card with existing ephemeral wallet
    if carte.wallet_ephemere:
        return carte.wallet_ephemere

    # 3. Pas de wallet local connu → on demande a Fedow (source de verite) le
    # wallet de la carte et on le miroir (meme uuid). Obligatoire pour pouvoir
    # recevoir du FED. On ne fabrique PLUS de wallet local a uuid aleatoire :
    # sinon doublon deconnecte de Fedow, impossible d'y charger du FED.
    # / No known local wallet → ask Fedow (source of truth) and mirror its uuid.
    wallet = obtenir_wallet_carte_depuis_fedow(carte)
    if wallet is None:
        raise Exception(
            f"Carte {carte.tag_id} inconnue de Fedow (ou Fedow indisponible). "
            f"Elle doit etre provisionnee dans Fedow avant usage."
        )
    return wallet


def lire_depensable_fed_frais(user):
    """
    Lit le solde FED dépensable d'un user EN TEMPS RÉEL (sans cache) sur le Fedow distant.
    / Reads a user's spendable FED balance in real time (no cache) from the remote Fedow.

    LOCALISATION : laboutik/views.py

    POURQUOI un helper dédié : ce solde sert à DEUX endroits — l'affichage du solde complet
    (obtenir_solde_complet_carte) ET la cascade de paiement (le FED comme cran transparent).
    Dans les deux cas on veut le solde FRAIS (le FED peut être débité juste après), donc
    `use_cache=False`. Dégradé en silence si le Fedow ne répond pas (jamais de blocage).
    / Dedicated helper because this balance is used in TWO places: full-balance display AND the
    payment cascade (FED as a transparent tier). Both need a FRESH value (FED may be spent right
    after), hence use_cache=False. Degraded silently if Fedow is unreachable (never blocks).

    :param user: TibilletUser (la carte doit être liée ; ne pas appeler si user is None)
    :return: tuple (fed_centimes: int, fed_disponible: bool)
        fed_disponible=False si pas de place Fedow ou Fedow injoignable.
    """
    try:
        fedow_config = FedowConfig.get_solo()
        # On teste can_fedow() AVANT d'instancier FedowAPI : sinon, sur un tenant sans place,
        # l'instanciation déclencherait une création de place (effet de bord).
        # / Check can_fedow() BEFORE instantiating FedowAPI (avoids a place creation side effect).
        if not fedow_config.can_fedow():
            return 0, False
        fedow_api = FedowAPI(fedow_config=fedow_config)
        fed_centimes = int(
            fedow_api.wallet.get_total_fiducial_and_all_federated_token(user, use_cache=False)
        )
        return fed_centimes, True
    except Exception as erreur_fedow:
        # Fedow injoignable ou lent : on dégrade en silence.
        # / Fedow unreachable or slow: degrade silently.
        logger.warning(f"lire_depensable_fed_frais : solde FED indisponible — {erreur_fedow}")
        return 0, False


def obtenir_solde_complet_carte(carte):
    """
    Lit le solde complet d'une carte : monnaies locales (fedow_core) + solde FED du réseau (Fedow).
    / Reads a card's full balance: local currencies (fedow_core) + FED network balance (Fedow).

    LOCALISATION : laboutik/views.py

    POURQUOI : au POS V2, une carte peut porter deux sortes de monnaie :
    - les monnaies locales du lieu, stockées dans la base locale (fedow_core) ;
    - le solde FED du réseau fédéré, stocké sur le serveur Fedow distant.
    On veut afficher (et plus tard débiter) les DEUX, donc on lit les deux sources.

    Le solde FED est lu EN TEMPS RÉEL (sans cache) car il peut servir tout de suite à un
    paiement. Si le Fedow ne répond pas, on dégrade en silence : on garde les soldes locaux
    et on signale le réseau comme indisponible (jamais de blocage de la vente).

    / At a V2 POS, a card may carry two kinds of money: local currencies (fedow_core, local DB)
    / and the FED network balance (remote Fedow). We read both. The FED balance is read in real
    / time (no cache) as it may be spent right away; degraded silently if Fedow is unreachable.

    :param carte: CarteCashless
    :return: dict avec / dict with
        - tokens_locaux : liste de dicts (asset_name, asset_category, value_euros, provenance)
        - locaux_centimes : total des monnaies locales (int, centimes)
        - fed_centimes : solde FED dépensable (int, centimes), 0 si indisponible
        - fed_disponible : bool, False si carte anonyme / pas de place Fedow / Fedow injoignable
        - total_centimes : locaux_centimes + fed_centimes (int, centimes)
    """
    # Wallet local de la carte (crée un éphémère si la carte est anonyme).
    # / Card's local wallet (creates an ephemeral one if the card is anonymous).
    wallet = _obtenir_ou_creer_wallet(carte)

    # 1. Monnaies locales : on lit tous les tokens du wallet dans la base locale (fedow_core).
    # 1. Local currencies: read all wallet tokens from the local database (fedow_core).
    tokens_locaux = []
    locaux_centimes = 0
    for token in WalletService.obtenir_tous_les_soldes(wallet):
        # Ignore token with 0 value
        if token.value == 0:
            continue

        tokens_locaux.append(
            {
                "asset_name": token.asset.name,
                "asset_category": token.asset.category,
                # Affichage uniquement (formate par floatformat cote template) : le
                # total reellement depensable reste calcule en centimes entiers
                # (locaux_centimes ci-dessous), jamais a partir de ce float.
                # / Display only (floatformat in template); the spendable total stays
                # in integer cents (locaux_centimes), never derived from this float.
                "value_euros": token.value / 100,
                "provenance": token.asset.tenant_origin.name,
            }
        )
        locaux_centimes += token.value

    # 2. Solde FED du réseau : uniquement si la carte est liée à un user (signature RSA).
    #    Délégué à lire_depensable_fed_frais (lecture fraîche, dégradée si Fedow injoignable).
    # 2. FED network balance: only if the card is linked to a user. Delegated to
    #    lire_depensable_fed_frais (fresh read, degraded if Fedow is unreachable).
    fed_centimes = 0
    fed_disponible = False
    if carte.user is not None:
        fed_centimes, fed_disponible = lire_depensable_fed_frais(carte.user)

    return {
        "tokens_locaux": tokens_locaux,
        "locaux_centimes": locaux_centimes,
        "fed_centimes": fed_centimes,
        "fed_disponible": fed_disponible,
        "total_centimes": locaux_centimes + fed_centimes,
    }


def _soldes_locaux_pour_affichage(wallet):
    """
    Liste les soldes locaux d'un wallet, prets pour l'affichage en pastilles.
    / Lists a wallet's local balances, ready for pill display.

    LOCALISATION : laboutik/views.py

    Lecture locale seulement (fedow_core), sans appel au Fedow distant :
    l'ecran « fonds insuffisants » doit s'afficher tout de suite.
    / Local read only, no remote Fedow call: the screen must show at once.

    Utilise par / Used by : _payer_par_nfc() → hx_funds_insufficient.html

    :param wallet: Wallet de la carte
    :return: liste de dicts {asset_name, asset_category, value_euros}
    """
    soldes_pour_affichage = []
    for token in WalletService.obtenir_tous_les_soldes(wallet):
        soldes_pour_affichage.append(
            {
                "asset_name": token.asset.name,
                "asset_category": token.asset.category,
                "value_euros": token.value / 100,
            }
        )
    return soldes_pour_affichage


def _repartir_legacy_sur_articles(lignes_complement, transactions_legacy):
    """
    Répartit les transactions du débit legacy (renvoyées par Fedow) sur les parts d'articles
    NON couvertes par les monnaies locales, en gardant chaque asset / moyen de paiement DISTINCT.
    / Distributes the legacy debit transactions (returned by Fedow) over the article parts NOT
    covered by local currencies, keeping each asset / payment method DISTINCT.

    LOCALISATION : laboutik/views.py

    POURQUOI la distinction fine : les monnaies LOCALES (TLF) sont gérées par les LIEUX, la
    monnaie FÉDÉRÉE (FED) est gérée par la COOPÉRATIVE. Un débit legacy peut puiser dans les deux
    (TLF fédérés d'autres lieux → `LOCAL_EURO`, et FED → `STRIPE_FED`). On crée donc une
    LigneArticle par (article, asset legacy) avec le BON moyen de paiement, pour que la compta
    attribue chaque euro au bon responsable.
    / LOCAL currencies (TLF) are managed by the VENUES, the FEDERATED currency (FED) by the
    COOPERATIVE. A legacy debit can draw from both; we keep them finely distinct for accounting.

    :param lignes_complement: liste de tuples (article_dict, None, montant_centimes, None)
        — les parts d'articles non couvertes par les locaux (asset=None), dans l'ordre.
    :param transactions_legacy: liste de tuples (asset_uuid, montant_centimes, payment_method,
        uuid_de_la_transaction) rendus par `_debiter_legacy` — ce que Fedow a réellement débité
        (1 par asset legacy), moyen déjà résolu, dans l'ordre. Seuls les trois premiers
        éléments servent ici : l'uuid de la transaction sert aux RÈGLEMENTS, que l'appelant
        écrit directement depuis `transactions_legacy` (une part d'article perd le lien avec
        sa transaction).
        INVARIANT : somme des montants legacy == somme des montants de lignes_complement.
    :return: liste de tuples (article_dict, asset_uuid, montant_centimes, payment_method)
        — 1 par recouvrement (article × transaction), prête pour _creer_lignes_articles_cascade.
    """
    lignes_legacy = []

    # File des transactions à consommer, dans l'ordre renvoyé par Fedow (mutable : on décrémente).
    # On lit les trois premiers éléments par leur position : un éventuel élément de plus
    # (l'uuid de la transaction) est ignoré ici.
    # / Queue of transactions to consume, in Fedow's order (mutable: we decrement amounts).
    #   The first three elements are read by position: an extra element (the uuid) is ignored.
    file_transactions = []
    for transaction_legacy in transactions_legacy:
        asset_uuid = transaction_legacy[0]
        montant = transaction_legacy[1]
        payment_method = transaction_legacy[2]
        file_transactions.append([asset_uuid, montant, payment_method])
    index_transaction = 0

    # Pour chaque part d'article à couvrir, on pioche dans les transactions tant qu'il reste
    # un montant à couvrir. Une part peut être couverte par plusieurs transactions (donc
    # plusieurs LigneArticle), et une transaction peut couvrir plusieurs articles.
    # / For each article part, draw from transactions until covered. A part may span several
    # transactions (several LigneArticle); a transaction may cover several articles.
    for (article, _asset_none, montant_article, _pm_none) in lignes_complement:
        reste_a_couvrir = montant_article
        while reste_a_couvrir > 0:
            asset_uuid, montant_transaction, payment_method = file_transactions[index_transaction]
            couvert = min(reste_a_couvrir, montant_transaction)
            lignes_legacy.append((article, asset_uuid, couvert, payment_method))
            reste_a_couvrir -= couvert
            file_transactions[index_transaction][1] -= couvert
            # Transaction épuisée → on passe à la suivante.
            # / Transaction exhausted → move to the next one.
            if file_transactions[index_transaction][1] == 0:
                index_transaction += 1

    return lignes_legacy


def _decouper_lignes_complement(lignes_complement, montant_a_couvrir):
    """
    Découpe les lignes complément (asset=None) en deux : la part couverte par `montant_a_couvrir`
    (ex: le FED disponible) et le reste (qui ira en espèces/CB).
    / Splits the complement lines (asset=None) in two: the part covered by `montant_a_couvrir`
    (e.g. the available FED) and the rest (which will be paid by cash/CC).

    LOCALISATION : laboutik/views.py

    Sert au paiement COMPLÉMENTAIRE : quand la carte a un peu de FED mais pas assez, le FED couvre
    `montant_a_couvrir` centimes des articles non couverts par les locaux, et le solde restant est
    réglé par le moyen complémentaire (espèces, CB).
    / Used for the COMPLEMENT payment: FED covers `montant_a_couvrir`, the rest by cash/CC.

    :param lignes_complement: liste de tuples (article_dict, None, montant_centimes, None)
    :param montant_a_couvrir: int — centimes que le FED va couvrir (≤ somme des lignes_complement)
    :return: tuple (lignes_couvertes, lignes_reste), même format de tuples, l'une comme l'autre.
        lignes_couvertes : la part FED (somme == montant_a_couvrir).
        lignes_reste : la part restante (espèces/CB).
    """
    lignes_couvertes = []
    lignes_reste = []
    restant_a_couvrir = montant_a_couvrir
    for (article, _none, montant, _pm) in lignes_complement:
        if restant_a_couvrir >= montant:
            # Toute la part de cet article est couverte par le FED.
            # / This whole article part is covered by FED.
            lignes_couvertes.append((article, None, montant, None))
            restant_a_couvrir -= montant
        elif restant_a_couvrir > 0:
            # Cet article est coupé en deux : une part FED, une part complément.
            # / This article is split: a FED part and a complement part.
            lignes_couvertes.append((article, None, restant_a_couvrir, None))
            lignes_reste.append((article, None, montant - restant_a_couvrir, None))
            restant_a_couvrir = 0
        else:
            # Plus de FED disponible : tout en complément.
            # / No FED left: everything goes to complement.
            lignes_reste.append((article, None, montant, None))
    return lignes_couvertes, lignes_reste


def _categorie_asset_transaction(transaction, fedow_api):
    """
    Catégorie de l'asset d'une transaction legacy ('FED', 'TLF', ...).
    / Asset category of a legacy transaction.

    LOCALISATION : laboutik/views.py

    Si Fedow a renvoyé l'asset sérialisé dans la transaction, on lit la catégorie dedans (zéro
    appel). Sinon, on la récupère via un appel Fedow (`asset.retrieve`), comme le flux QR V1.
    / If Fedow returned the serialized asset inline, read the category from it (no call). Otherwise
    fetch it via a Fedow call, like the V1 QR flow.
    """
    asset_serialise = transaction.get("serialized_asset")
    if asset_serialise and asset_serialise.get("category"):
        return asset_serialise["category"]
    asset_info = fedow_api.asset.retrieve(str(transaction["asset"]))
    return asset_info["category"]


def _calculer_soldes_apres_paiement(wallet, lignes_debitees):
    """
    Construit l'avant / apres de la carte pour l'ecran de succes.
    / Builds the card's before / after for the success screen.

    LOCALISATION : laboutik/views.py

    Pour chaque monnaie (Asset local) debitee pendant la vente, on donne :
    - ce qui a ete paye avec cette monnaie ;
    - le solde apres la vente (lu dans le wallet) ;
    - le solde avant le paiement = solde apres + montant paye.

    Le solde « avant » est calcule, pas lu avant le debit. Ainsi on a toujours
    avant - paye = apres a l'ecran, meme si le panier contenait une recharge
    offerte creditee juste avant les debits.
    / "Before" is computed (after + paid), so before - paid = after on screen,
      even when a free top-up was credited just before the debits.

    Les lignes legacy (Fedow) portent un uuid d'asset distant, pas un Asset
    local : elles sont ignorees, comme avant (leur solde n'etait pas affiche).
    / Legacy lines carry a remote asset uuid, not a local Asset: skipped, as before.

    APPELE PAR : PaiementViewSet (paiement NFC, paiement complementaire, 2e carte).
    Les appelants regroupent ensuite le resultat par carte dans cartes_apres_paiement.
    AFFICHE PAR : laboutik/templates/laboutik/partial/_succes_carte.html

    :param wallet: wallet de la carte debitee
    :param lignes_debitees: tuples (article, asset, montant_centimes, payment_method)
    :return: liste de dicts, dans l'ordre de la cascade :
        name, unite (nom de la monnaie pour des points ou du temps, sinon vide),
        solde_euros (garde pour nouveau_solde), solde_avant_centimes,
        debite_centimes, solde_centimes
    """
    from collections import OrderedDict

    # Additionne ce qui a ete paye, monnaie par monnaie, dans l'ordre de la cascade
    # / Sum what was paid, currency by currency, in cascade order
    montant_paye_par_asset = OrderedDict()
    for _article, asset_de_la_ligne, montant_de_la_ligne, _moyen in lignes_debitees:
        ligne_sur_un_asset_local = isinstance(asset_de_la_ligne, Asset)
        if not ligne_sur_un_asset_local:
            continue
        if asset_de_la_ligne not in montant_paye_par_asset:
            montant_paye_par_asset[asset_de_la_ligne] = 0
        montant_paye_par_asset[asset_de_la_ligne] += montant_de_la_ligne

    soldes_apres_paiement = []
    for asset_debite, montant_paye_en_centimes in montant_paye_par_asset.items():
        solde_apres_en_centimes = WalletService.obtenir_solde(
            wallet=wallet, asset=asset_debite
        )
        # Somme presente sur la carte avant ce paiement
        # / Balance on the card before this payment
        solde_avant_en_centimes = solde_apres_en_centimes + montant_paye_en_centimes

        # Unite des montants de cette monnaie : son nom pour des points ou du
        # temps (filtre montant_dans_la_monnaie), vide pour de l'argent (euros).
        # / Unit of this currency's amounts: its name for points/time, empty for money.
        unite_de_la_monnaie = ""
        if asset_debite.category in (Asset.TIM, Asset.FID):
            unite_de_la_monnaie = asset_debite.name

        soldes_apres_paiement.append(
            {
                "name": asset_debite.name,
                "unite": unite_de_la_monnaie,
                "solde_euros": solde_apres_en_centimes / 100,
                "solde_avant_centimes": solde_avant_en_centimes,
                "debite_centimes": montant_paye_en_centimes,
                "solde_centimes": solde_apres_en_centimes,
            }
        )
    return soldes_apres_paiement


def _debiter_legacy(user, montant_centimes, uuid_transaction):
    """
    Débite le legacy (FED + TLF fédérés) via Fedow et renvoie les transactions, moyen DÉJÀ résolu.
    / Debits the legacy (FED + federated TLF) via Fedow; returns transactions with resolved method.

    LOCALISATION : laboutik/views.py

    `to_place_from_qrcode(asset_type="EURO")` lance la cascade legacy CÔTÉ SERVEUR Fedow (TLF
    fédérés d'abord, puis FED) et renvoie UNE liste de transactions (1 par asset débité). Pour
    chaque transaction, on résout le moyen de paiement selon la catégorie de l'asset — distinction
    FINE car la responsabilité diffère :
    - FED (monnaie fédérée, gérée par la COOPÉRATIVE) → `STRIPE_FED`
    - TLF (monnaie locale d'un autre lieu, fédérée, gérée par les LIEUX) → `LOCAL_EURO`
    / Fedow runs the legacy cascade server-side and returns one transaction per debited asset.
    We resolve the payment method per asset category (who holds the money differs).

    Lève une Exception si le débit échoue (solde insuffisant côté Fedow, réseau injoignable) :
    fail-fast, AUCUN débit partiel — l'appelant rebascule alors sur le complément.
    / Raises on failure: fail-fast, NO partial debit — caller falls back to complement.

    :param user: TibilletUser (carte liée, signable)
    :param montant_centimes: int — montant à débiter
    :param uuid_transaction: UUID de la vente POS (traçabilité POS ↔ Fedow)
    :return: liste de tuples (asset_uuid, montant_centimes, payment_method,
        uuid_de_la_transaction). L'uuid de la transaction distante sert au règlement de la
        vente (`reference_externe`) et au journal d'incident.
    """
    fedow_api = FedowAPI()
    transactions = fedow_api.transaction.to_place_from_qrcode(
        user=user,
        amount=montant_centimes,
        asset_type="EURO",
        comment=f"Vente POS {uuid_transaction}",
        metadata={"uuid_transaction": str(uuid_transaction)},
    )
    if not transactions:
        raise Exception("Débit legacy : Fedow n'a renvoyé aucune transaction")

    transactions_legacy = []
    for transaction in transactions:
        categorie = _categorie_asset_transaction(transaction, fedow_api)
        # 'FED' = monnaie fédérée (coopérative) ; 'TLF' = monnaie locale fédérée (lieux).
        # / 'FED' = federated currency (cooperative); 'TLF' = federated local currency (venues).
        if categorie == "FED":
            payment_method = PaymentMethod.STRIPE_FED
        elif categorie == "TLF":
            payment_method = PaymentMethod.LOCAL_EURO
        else:
            raise Exception(f"Débit legacy : catégorie d'asset inattendue '{categorie}'")
        transactions_legacy.append(
            (
                transaction["asset"],
                transaction["amount"],
                payment_method,
                transaction["uuid"],
            )
        )
    return transactions_legacy


class CarteVideeSurLAncienFedowReponseIllisible(Exception):
    """
    La carte EST vidée sur l'ancien Fedow (`card/refund` a réussi), mais la caisse ne
    sait pas lire ce qui a été repris (catégorie ou nom d'une monnaie).
    / The card IS emptied on the old Fedow, but the register cannot read what was
    taken back.

    LOCALISATION : laboutik/views.py

    Elle est distincte de toute autre erreur de l'ancien Fedow : après elle, la carte
    est vidée là-bas et un nouvel essai ne rendrait jamais cet argent. La caisse ne
    doit donc pas dire « rien n'a été fait : réessayez », mais la vérité : vidée sur
    l'ancien Fedow, pas en local, incident enregistré.
    / Distinct from any other old-Fedow error: the card is emptied there and a retry
    would never give this money back. The screen must tell the truth.

    LEVÉE PAR : _vider_la_carte_sur_l_ancien_fedow (après avoir journalisé l'INCIDENT)
    ATTRAPÉE PAR : PaiementViewSet.vider_carte
    """


def _vider_la_carte_sur_l_ancien_fedow(carte_client, tag_id_carte_primaire, vider_et_delier):
    """
    Vide la carte du client sur l'ancien Fedow (serveur distant), AVANT le Fedow local.
    / Empties the customer card on the old Fedow (remote server), BEFORE the local Fedow.

    LOCALISATION : laboutik/views.py

    Appel réseau : à faire HORS de toute transaction de base. Un vidage distant ne
    s'annule pas.
    / Network call: OUTSIDE any database transaction. A remote emptying cannot be undone.

    - Lieu non relié à l'ancien Fedow : rien n'est appelé, rend None. On teste
      `can_fedow()` AVANT de créer `FedowAPI` : sur un lieu sans place Fedow, sa
      création lancerait une création de place sur le serveur.
    - Carte inconnue de l'ancien Fedow (réponse 404, `CarteInconnueDeFedow`) : rend
      None, la caisse vide le Fedow local seul.
    - Carte connue : elle est TOUJOURS envoyée à `card/refund`, même sans solde
      là-bas : sinon « vider et délier » (VOID) ne la délierait jamais. Rend la liste
      des transactions reprises (vide si la carte n'avait rien là-bas).
    - `card/refund` réussit, puis ce qui a été repris est illisible : INCIDENT
      journalisé, puis `CarteVideeSurLAncienFedowReponseIllisible` (la carte EST vidée
      là-bas).
    - Toute autre erreur (serveur injoignable, refus) remonte : rien n'est fait.
    / Venue not linked or card unknown (404): None. Known card: always sent to
      card/refund, returns the (possibly empty) list. Refund done but unreadable:
      INCIDENT logged, then CarteVideeSurLAncienFedowReponseIllisible. Any other error
      is raised.

    La même carte primaire sert aux deux Fedow : son tag est envoyé tel quel.
    / The same primary card is used for both Fedow servers.

    APPELÉ PAR : PaiementViewSet.vider_carte

    :param carte_client: CarteCashless à vider
    :param tag_id_carte_primaire: tag de la carte primaire du caissier
    :param vider_et_delier: True → action VOID (délie aussi la carte), sinon REFUND
    :return: None si la carte n'est pas envoyée à l'ancien Fedow ; sinon une liste
        de dicts, un par transaction REFUND de l'ancien Fedow :
        {"uuid", "asset" (uuid de la monnaie distante), "montant" (centimes),
        "categorie" ("TLF" monnaie locale du lieu, "TNF" jetons cadeau, "FED"),
        "nom" (nom de la monnaie), "code_monnaie" (ex. "EUR", ou "" si inconnu)}
    :raises CarteVideeSurLAncienFedowReponseIllisible: carte vidée là-bas, réponse
        illisible
    :raises Exception: l'ancien Fedow échoue, rien n'est fait
    """
    if not FedowConfig.get_solo().can_fedow():
        return None

    fedow_api = FedowAPI()
    try:
        fedow_api.NFCcard.retrieve(carte_client.tag_id)
    except CarteInconnueDeFedow:
        return None

    reponse_du_vidage = fedow_api.NFCcard.refund(
        user_card_firstTagId=carte_client.tag_id,
        primary_card_fisrtTagId=tag_id_carte_primaire,
        void=vider_et_delier,
    )
    transactions_rendues = reponse_du_vidage["serialized_transactions"]

    # La catégorie et le nom de chaque monnaie reprise se lisent dans le portefeuille
    # d'avant le vidage, rendu dans la même réponse (aucun appel réseau de plus). Les
    # transactions du vrai serveur n'ont pas de fiche de monnaie.
    # / Each currency's category and name are read in the before-refund wallet.
    jeton_avant_le_vidage_par_monnaie = {}
    portefeuille_avant_le_vidage = reponse_du_vidage.get("before_refund_serialized_wallet") or {}
    for jeton in portefeuille_avant_le_vidage.get("tokens", []):
        jeton_avant_le_vidage_par_monnaie[str(jeton["asset_uuid"])] = jeton

    transactions_de_l_ancien_fedow = []
    try:
        for transaction_rendue in transactions_rendues:
            jeton_avant_le_vidage = jeton_avant_le_vidage_par_monnaie.get(
                str(transaction_rendue["asset"])
            )
            if jeton_avant_le_vidage is not None:
                categorie = jeton_avant_le_vidage["asset_category"]
                nom_de_la_monnaie = jeton_avant_le_vidage.get("asset_name") or ""
                fiche_de_la_monnaie = jeton_avant_le_vidage.get("asset") or {}
                code_de_la_monnaie = fiche_de_la_monnaie.get("currency_code") or ""
            else:
                # Monnaie absente du portefeuille renvoyé : on demande sa fiche.
                # / Currency missing from the returned wallet: ask for its record.
                fiche_de_la_monnaie = fedow_api.asset.retrieve(str(transaction_rendue["asset"]))
                categorie = fiche_de_la_monnaie["category"]
                nom_de_la_monnaie = fiche_de_la_monnaie["name"]
                code_de_la_monnaie = fiche_de_la_monnaie.get("currency_code") or ""
            transactions_de_l_ancien_fedow.append(
                {
                    "uuid": transaction_rendue["uuid"],
                    "asset": transaction_rendue["asset"],
                    "montant": transaction_rendue["amount"],
                    "categorie": categorie,
                    "nom": nom_de_la_monnaie,
                    "code_monnaie": code_de_la_monnaie,
                }
            )
    except Exception as erreur_de_lecture:
        # La carte EST vidée sur l'ancien Fedow, mais on ne sait pas lire ce qui a été
        # repris : rien n'est écrit en local, régularisation à la main.
        # / The card IS emptied on the old Fedow, but the result cannot be read.
        uuids_des_transactions = []
        for transaction_rendue in transactions_rendues:
            uuids_des_transactions.append(str(transaction_rendue["uuid"]))
        logger.error(
            f"INCIDENT ancien Fedow vidé, catégories illisibles — "
            f"carte={carte_client.tag_id} "
            f"transactions_ancien_fedow={', '.join(uuids_des_transactions)} : "
            f"régularisation manuelle requise. ({erreur_de_lecture})"
        )
        raise CarteVideeSurLAncienFedowReponseIllisible(
            f"Carte {carte_client.tag_id} vidée sur l'ancien Fedow, réponse illisible."
        ) from erreur_de_lecture

    return transactions_de_l_ancien_fedow


def _ecrire_la_vente_du_vidage(
    request,
    point_de_vente,
    carte_client,
    client_de_la_vente,
    transactions_locales,
    transactions_de_l_ancien_fedow,
):
    """
    Écrit la vente `VIDAGE_CARTE` d'un vidage de carte :
    - un règlement POSITIF par remboursement d'argent, puis un règlement espèces de
      MOINS le total rendu ;
    - par transaction de jetons cadeau repris : un règlement « jetons » (LG) POSITIF
      et un article « Jetons cadeau repris au vidage » du même montant.
    / Writes the card-emptying sale: one POSITIVE payment per money refund, then minus
    the total in cash; per gift-token transaction, a positive LG payment and a "gift
    tokens taken back" item of the same amount.

    LOCALISATION : laboutik/views.py

    À appeler DANS le `transaction.atomic()` du vidage local. L'appelant encaisse la
    vente (`encaisser_vente`) en dernier.
    / Call INSIDE the local emptying atomic block. The caller settles the sale last.

    Règlements :
    - transaction locale (`fedow_core`) : son uuid dans `fedow_transaction_uuid` ;
    - transaction de l'ancien Fedow (serveur distant) : son uuid dans
      `reference_externe` ;
    - monnaie locale du lieu → `LE`, monnaie fédérée → `SF`, jetons cadeau → `LG` ;
      chacun avec sa monnaie et la carte.
    Jetons cadeau : des jetons perdus annulent la dette du lieu envers le porteur
    (D8 bis). Aucun argent ne sort du tiroir pour eux. L'article « Jetons cadeau
    repris au vidage » (produit système, `NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE`) est hors
    chiffre d'affaires, TVA 0, quantité 1, prix = montant, sans carte ni monnaie ; le
    plan comptable le reconnaît par son nom (623400). Les deux égalités tiennent :
    Σ règlements = Σ articles = le total des jetons repris.
    Une carte qui n'a QUE des jetons cadeau écrit aussi sa vente (aucun règlement
    espèces). Aucun argent ni aucun jeton repris : AUCUNE vente.
    / Local uuid in fedow_transaction_uuid, remote uuid in reference_externe. Gift
    tokens: lost tokens cancel the venue's debt (D8 bis): LG payment + off-revenue,
    0-VAT item. A card with tokens only also writes its sale; nothing taken back → no
    sale.

    APPELÉ PAR : PaiementViewSet.vider_carte

    :param client_de_la_vente: le titulaire de la carte, lu AVANT le vidage (« vider et
        délier » le retire de la carte)
    :param transactions_locales: les `Transaction` REFUND du Fedow local
    :param transactions_de_l_ancien_fedow: les dicts de `_vider_la_carte_sur_l_ancien_fedow`
    :return: la `Vente` EN_ATTENTE, ou None s'il n'y a rien de repris
    """
    # Les remboursements d'argent et les jetons cadeau repris, des deux Fedow :
    # (moyen, montant, asset, portefeuille, uuid local, référence distante).
    # / Money refunds and gift tokens taken back, from both Fedow servers.
    remboursements_d_argent = []
    jetons_cadeau_repris = []
    for transaction_locale in transactions_locales:
        categorie_locale = transaction_locale.asset.category
        if categorie_locale == Asset.TNF:
            jetons_cadeau_repris.append(
                (
                    PaymentMethod.LOCAL_GIFT,
                    transaction_locale.amount,
                    transaction_locale.asset.uuid,
                    transaction_locale.sender,
                    transaction_locale.uuid,
                    "",
                )
            )
            continue
        if categorie_locale == Asset.TLF:
            moyen_du_reglement = PaymentMethod.LOCAL_EURO
        elif categorie_locale == Asset.FED:
            moyen_du_reglement = PaymentMethod.STRIPE_FED
        else:
            continue
        remboursements_d_argent.append(
            (
                moyen_du_reglement,
                transaction_locale.amount,
                transaction_locale.asset.uuid,
                transaction_locale.sender,
                transaction_locale.uuid,
                "",
            )
        )
    for transaction_distante in transactions_de_l_ancien_fedow:
        categorie_distante = transaction_distante["categorie"]
        if categorie_distante == "TNF":
            moyen_du_reglement = PaymentMethod.LOCAL_GIFT
        elif categorie_distante == "TLF":
            moyen_du_reglement = PaymentMethod.LOCAL_EURO
        elif categorie_distante == "FED":
            moyen_du_reglement = PaymentMethod.STRIPE_FED
        else:
            continue
        reglement_de_la_transaction_distante = (
            moyen_du_reglement,
            transaction_distante["montant"],
            transaction_distante["asset"],
            None,
            None,
            str(transaction_distante["uuid"]),
        )
        if categorie_distante == "TNF":
            jetons_cadeau_repris.append(reglement_de_la_transaction_distante)
        else:
            remboursements_d_argent.append(reglement_de_la_transaction_distante)

    argent_rendu_en_centimes = 0
    for remboursement_d_argent in remboursements_d_argent:
        montant_rembourse = remboursement_d_argent[1]
        argent_rendu_en_centimes += montant_rembourse
    rien_n_est_repris = argent_rendu_en_centimes == 0 and len(jetons_cadeau_repris) == 0
    if rien_n_est_repris:
        return None

    vente = ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=Vente.Nature.VIDAGE_CARTE,
        point_de_vente=point_de_vente,
        operateur=_operateur_de_la_caisse(request, request.POST.get("tag_id_cm", "")),
        client=client_de_la_vente,
        carte=carte_client,
    )
    for (
        moyen_du_reglement,
        montant_rembourse,
        uuid_de_la_monnaie,
        portefeuille_de_la_carte,
        uuid_de_la_transaction_locale,
        reference_distante,
    ) in remboursements_d_argent + jetons_cadeau_repris:
        ajouter_reglement(
            vente,
            moyen=moyen_du_reglement,
            montant=montant_rembourse,
            asset=uuid_de_la_monnaie,
            carte=carte_client,
            wallet=portefeuille_de_la_carte,
            fedow_transaction_uuid=uuid_de_la_transaction_locale,
            reference_externe=reference_distante,
        )

    # Les jetons cadeau repris : un article par transaction, du même montant, hors
    # chiffre d'affaires, TVA 0. Il porte le moyen historique LG (jusqu'à la fiche H).
    # / Gift tokens taken back: one item per transaction, off revenue, 0 VAT.
    if jetons_cadeau_repris:
        tarif_vendu_des_jetons_repris = tarif_vendu_d_un_produit_systeme(
            NOM_JETONS_CADEAU_REPRIS_AU_VIDAGE
        )
        for jeton_cadeau_repris in jetons_cadeau_repris:
            montant_des_jetons_repris = jeton_cadeau_repris[1]
            ajouter_article(
                vente,
                pricesold=tarif_vendu_des_jetons_repris,
                quantite=Decimal("1"),
                prix_unitaire=montant_des_jetons_repris,
                taux_tva=Decimal("0"),
                hors_chiffre_affaires=True,
                payment_method=PaymentMethod.LOCAL_GIFT,
                status=LigneArticle.VALID,
                point_de_vente=point_de_vente,
            )

    # L'argent sort du tiroir : un seul règlement espèces, négatif. Une carte qui n'a
    # que des jetons cadeau ne rend aucun argent : pas de règlement espèces.
    # / Cash leaves the drawer: one negative cash payment, none for tokens only.
    if argent_rendu_en_centimes != 0:
        ajouter_reglement(
            vente,
            moyen=PaymentMethod.CASH,
            montant=-argent_rendu_en_centimes,
        )
    return vente


def _ligne_de_vidage(nom_de_la_monnaie, montant_centimes, categorie, code_de_la_monnaie):
    """
    Une ligne de l'aperçu, de l'écran de succès ou du reçu d'un vidage de carte : une
    monnaie reprise, sur un des deux Fedow.
    / One line of a card-emptying preview, success screen or receipt.

    LOCALISATION : laboutik/views.py

    Seules la monnaie locale (TLF) et la monnaie fédérée (FED) sont de l'argent rendu.
    Les jetons cadeau (TNF) sont repris, sans argent.
    `currency_code` porte le nom attendu par le filtre `cents_to_asset`.
    / Only TLF and FED are money given back. Gift tokens (TNF) carry no money.

    APPELÉ PAR : vider_carte_preview, vider_carte
    """
    return SimpleNamespace(
        nom=nom_de_la_monnaie,
        montant_centimes=montant_centimes,
        est_de_l_argent_rendu=categorie in (Asset.TLF, Asset.FED),
        est_un_jeton_cadeau=categorie == Asset.TNF,
        currency_code=code_de_la_monnaie,
    )


def _lire_la_carte_sur_l_ancien_fedow(carte_client):
    """
    Lit, SANS RIEN DÉBITER, ce que le vidage reprendrait sur l'ancien Fedow.
    / Reads, WITHOUT DEBITING, what the emptying would take back on the old Fedow.

    LOCALISATION : laboutik/views.py

    Lecture : `NFCcard.retrieve(tag_id)` (GET `card/{tag_id}/`, le « check carte » de
    l'ancien Fedow). On garde les jetons que `card/refund` reprendrait
    (../Fedow/fedow_core/serializers.py, `CardRefundOrVoidValidator`) : solde positif,
    et monnaie fédérée, ou monnaie locale / jetons cadeau créés par CE lieu (monnaie
    dont le portefeuille d'origine est celui du lieu sur l'ancien Fedow).
    / Keeps the tokens card/refund would take: FED, or the venue's own TLF / TNF.

    EFFET DE BORD ACCEPTÉ : les validateurs de `fedow_connect` écrivent des miroirs
    locaux (portefeuille, fiche de monnaie, empreinte de transaction), comme pour la
    vidange elle-même.
    / Accepted side effect: fedow_connect validators write local mirrors.

    APPELÉ PAR : PaiementViewSet.vider_carte_preview

    :param carte_client: CarteCashless scannée
    :return: SimpleNamespace(
        statut : "absente" (lieu non relié, ou carte inconnue là-bas : réponse 404),
                 "injoignable" (toute autre erreur) ou "connue",
        jetons : liste des jetons repris (dicts `TokenValidator`), vide sauf "connue")
    """
    # On teste `can_fedow()` AVANT de créer `FedowAPI` : sur un lieu sans place Fedow,
    # sa création lancerait une création de place sur le serveur.
    # / Check can_fedow() BEFORE building FedowAPI.
    configuration_fedow = FedowConfig.get_solo()
    if not configuration_fedow.can_fedow():
        return SimpleNamespace(statut="absente", jetons=[])

    try:
        fiche_de_la_carte = FedowAPI().NFCcard.retrieve(carte_client.tag_id)
    except CarteInconnueDeFedow:
        return SimpleNamespace(statut="absente", jetons=[])
    except Exception as erreur_de_lecture:
        logger.warning(
            f"Aperçu du vidage : ancien Fedow injoignable pour la carte "
            f"{carte_client.tag_id} : {erreur_de_lecture}"
        )
        return SimpleNamespace(statut="injoignable", jetons=[])

    portefeuille_du_lieu = str(configuration_fedow.fedow_place_wallet_uuid)
    jetons_repris = []
    for jeton in fiche_de_la_carte["wallet"]["tokens"]:
        if jeton["value"] <= 0:
            continue
        categorie = jeton["asset_category"]
        monnaie_du_lieu = str(jeton["asset"].get("wallet_origin")) == portefeuille_du_lieu
        est_repris = categorie == Asset.FED or (
            categorie in (Asset.TLF, Asset.TNF) and monnaie_du_lieu
        )
        if est_repris:
            jetons_repris.append(jeton)
    return SimpleNamespace(statut="connue", jetons=jetons_repris)


def _relire_les_transactions_de_l_ancien_fedow(uuids_postes):
    """
    Relit sur l'ancien Fedow les transactions d'un vidage, pour le reçu.
    / Re-reads a card-emptying's transactions on the old Fedow, for the receipt.

    LOCALISATION : laboutik/views.py

    Le navigateur ne poste que des uuid : les montants, les monnaies et le
    destinataire viennent TOUJOURS de l'ancien Fedow (un montant posté se falsifie).
    On ne garde qu'une transaction de remboursement (REFUND ou VOID) reçue par le
    portefeuille du lieu. Tout autre uuid (inconnu, d'un autre lieu, pas un
    remboursement, mal formé, en double) est ignoré.
    / Only uuids are posted: amounts always come from the old Fedow. Only refunds
    received by the venue's wallet are kept; any other uuid is ignored.

    APPELÉ PAR : PaiementViewSet.vider_carte_imprimer_recu

    :param uuids_postes: les uuid postés par le formulaire d'impression
    :return: liste de dicts {"uuid", "montant", "categorie", "nom", "code_monnaie"}
    :raises Exception: l'ancien Fedow ne répond pas, ou répond mal. Le reçu n'est
        alors pas imprimé : jamais de reçu partiel.
    """
    if not uuids_postes:
        return []

    # Lieu non relié : aucune transaction de l'ancien Fedow n'est la sienne.
    # / Venue not linked: no old Fedow transaction belongs to it.
    configuration_fedow = FedowConfig.get_solo()
    if not configuration_fedow.can_fedow():
        return []

    fedow_api = FedowAPI()
    portefeuille_du_lieu = str(configuration_fedow.fedow_place_wallet_uuid)
    actions_de_remboursement = (TransactionValidator.REFUND, TransactionValidator.VOID)
    uuids_deja_lus = set()
    transactions_relues = []
    for uuid_poste in uuids_postes:
        try:
            uuid_de_la_transaction = str(uuid_module.UUID(str(uuid_poste)))
        except ValueError:
            continue
        if uuid_de_la_transaction in uuids_deja_lus:
            continue
        uuids_deja_lus.add(uuid_de_la_transaction)

        transaction_relue = fedow_api.transaction.retrieve(uuid_de_la_transaction)

        # CONTRAINTE : `TransactionFedow.retrieve` ne lève pas d'exception. Il rend les
        # données validées (un dict), OU le dict des erreurs de validation, OU le code
        # HTTP (un entier). 404 = transaction inconnue : ignorée. Tout le reste qui
        # n'est pas une transaction lisible est une panne : le reçu est refusé.
        # / TransactionFedow.retrieve never raises: it returns validated data, OR the
        # validation errors, OR the HTTP status code. 404 is ignored; anything else
        # unreadable is a failure.
        if transaction_relue == 404:
            continue
        transaction_lisible = isinstance(transaction_relue, dict) and isinstance(
            transaction_relue.get("amount"), int
        )
        if not transaction_lisible:
            raise Exception(
                f"Ancien Fedow : transaction {uuid_de_la_transaction} illisible "
                f"({transaction_relue})"
            )

        if transaction_relue.get("action") not in actions_de_remboursement:
            continue
        if str(transaction_relue.get("receiver")) != portefeuille_du_lieu:
            continue

        fiche_de_la_monnaie = fedow_api.asset.retrieve(str(transaction_relue["asset"]))
        categorie = fiche_de_la_monnaie["category"]
        if categorie not in (Asset.TLF, Asset.FED, Asset.TNF):
            continue
        transactions_relues.append(
            {
                "uuid": uuid_de_la_transaction,
                "montant": transaction_relue["amount"],
                "categorie": categorie,
                "nom": fiche_de_la_monnaie["name"],
                "code_monnaie": fiche_de_la_monnaie.get("currency_code") or "",
            }
        )
    return transactions_relues


def _render_erreur_toast(request, msg):
    """
    Rend un partial d'erreur compatible avec le pattern POS (toast dans #messages).
    / Renders an error partial compatible with POS toast pattern (in #messages).
    """
    contexte = {
        "msg_type": "warning",
        "msg_content": str(msg),
    }
    return render(request, "laboutik/partial/hx_messages.html", contexte)


def _valider_carte_primaire_pour_pv(tag_id_carte_manager, uuid_pv):
    """
    Vérifie que la carte primaire a accès au point de vente demandé.
    Checks that the primary card has access to the requested point of sale.

    LOCALISATION : laboutik/views.py

    :param tag_id_carte_manager: tag_id de la carte primaire (opérateur)
    :param uuid_pv: UUID du point de vente
    :raises PermissionDenied: si la carte n'a pas accès au PV
    """
    if not tag_id_carte_manager:
        # Pas de carte primaire (accès admin session) → pas de restriction PV
        # No primary card (admin session access) → no PV restriction
        return

    carte_primaire_obj, erreur = _charger_carte_primaire(tag_id_carte_manager)
    if erreur is not None:
        raise PermissionDenied(erreur)

    pv_autorise = carte_primaire_obj.points_de_vente.filter(uuid=uuid_pv).exists()
    if not pv_autorise:
        logger.warning(
            f"Carte primaire {tag_id_carte_manager} n'a pas accès au PV {uuid_pv}"
        )
        raise PermissionDenied(_("Accès non autorisé à ce point de vente"))


# Constantes : methodes de caisse qui representent des recharges cashless
# Constants: POS methods that represent cashless top-ups
#
# TROIS TYPES DE RECHARGE :
# - RE (Recharge Euros) : le client PAIE en especes/CB pour recevoir de la monnaie locale (TLF)
# - RC (Recharge Cadeau) : le caissier OFFRE de la monnaie cadeau (TNF) — pas de paiement
# - TM (Recharge Temps) : le caissier OFFRE du temps (TIM) — pas de paiement
#
# THREE TYPES OF TOP-UP:
# - RE (Euro top-up): the client PAYS cash/card to receive local currency (TLF)
# - RC (Gift top-up): the cashier GIVES gift currency (TNF) — no payment
# - TM (Time top-up): the cashier GIVES time currency (TIM) — no payment
METHODES_RECHARGE = (
    Product.RECHARGE_EUROS,
    Product.RECHARGE_CADEAU,
    # Product.RECHARGE_TEMPS,
)

# Recharges payantes : le client doit payer (especes, CB, cheque)
# Paid top-ups: the client must pay (cash, card, check)
METHODES_RECHARGE_PAYANTES = (Product.RECHARGE_EUROS,)

# Recharges gratuites : credit automatique, pas de paiement demande
# Free top-ups: auto-credit, no payment asked
METHODES_RECHARGE_GRATUITES = (Product.RECHARGE_CADEAU,)  # , Product.RECHARGE_TEMPS) — la virgule garde un tuple / trailing comma keeps a tuple


# Pictogramme de la tuile « Recharger » selon le type de recharge.
# Les noms sont ceux de cotton/V2/bt/paiement.html.
# / Top-up tile pictogram per top-up type (names from cotton/V2/bt/paiement.html).
ICONES_RECHARGE = {
    Product.RECHARGE_EUROS: "coins",
    Product.RECHARGE_CADEAU: "gift",
#    Product.RECHARGE_TEMPS: "clock",
}


def _produits_de_recharge_du_lieu():
    """
    Les produits de recharge utilisables dans ce lieu, avec leurs tarifs en euros.
    / The top-up products usable in this venue, with their EUR prices.

    LOCALISATION : laboutik/views.py

    REGLE (decision du 2026-09-18) : la recharge est possible depuis TOUS les
    points de vente, pas seulement ceux qui contiennent le produit (Cashless).
    La vente reste enregistree sur le point de vente ou elle a lieu.
    MAIS (decision du 2026-09-29) : le check carte ne propose la zone
    « Recharger » que si la carte primaire du caissier a au moins un point
    de vente cashless (voir _carte_primaire_a_un_point_de_vente_cashless).
    / Top-ups are allowed from EVERY POS, not only those holding the product.
    BUT the check card only shows the "Top up" zone when the primary card
    has a cashless POS.

    Un produit est retenu s'il est publie, non archive, et lie a un Asset
    actif et non archive (meme regle que l'ecran de vente).
    / Kept if published, not archived, linked to an active non-archived Asset.

    Utilise par / Used by :
    - _construire_contexte_recharge() : les tuiles « Recharger »
    - _extraire_articles_du_panier() : accepte ces produits hors M2M du PV

    :return: QuerySet de Product, avec l'attribut prix_euros (liste de Price)
    """
    tarifs_en_euros = Prefetch(
        "prices",
        queryset=Price.objects.filter(publish=True, asset__isnull=True).order_by(
            "order"
        ),
        to_attr="prix_euros",
    )
    return (
        Product.objects.filter(
            methode_caisse__in=METHODES_RECHARGE,
            publish=True,
            archive=False,
            asset__isnull=False,
            asset__archive=False,
            asset__active=True,
        )
        .select_related("asset")
        .prefetch_related(tarifs_en_euros)
        .order_by("poids", "name")
    )


def _construire_contexte_recharge(
    carte,
    point_de_vente,
    uuid_produit_choisi="",
    uuid_prix_choisi="",
    montant_libre_saisi=None,
):
    """
    Prepare les donnees de la zone « Recharger » de la popup check carte.
    / Builds the data of the "Top up" zone of the card check popup.

    LOCALISATION : laboutik/views.py

    La zone avance par etapes. Chaque clic renvoie la zone entiere,
    recalculee ici (HTMX, pas d'etat cote JS) :
    1. Choisir QUOI : une tuile par produit de recharge du lieu
       (monnaie locale RE, cadeau RC, temps TM), depuis n'importe quel PV,
       si la carte primaire a un PV cashless (sinon retour_carte passe None).
    2. Choisir COMBIEN : les tarifs du produit (1, 5, 10, Libre...).
    3. Montant libre : un champ de saisie (seulement si le tarif est libre).
    4. Confirmer : le montant, le solde apres recharge, puis
       - RE (payante) : les tuiles des moyens de paiement du point de vente ;
       - RC / TM (offertes) : un bouton « Offrir ».
    La recharge elle-meme n'est PAS faite ici : les boutons de l'etape 4
    postent vers payer() ou identifier_client(), qui existent deja.
    / The zone moves step by step (what, how much, free amount, confirm).
    The top-up itself is done by the existing payer() / identifier_client().

    Utilise par / Used by : PaiementViewSet.retour_carte() et
    PaiementViewSet.recharge_carte() → laboutik/partial/hx_card_recharge.html

    :param carte: CarteCashless scannee
    :param point_de_vente: PointDeVente courant, ou None (pas de recharge alors).
        retour_carte() passe None si la carte primaire n'a aucun PV cashless
        (voir _carte_primaire_a_un_point_de_vente_cashless).
    :param uuid_produit_choisi: uuid (str) du produit choisi a l'etape 1
    :param uuid_prix_choisi: uuid (str) du tarif choisi a l'etape 2
    :param montant_libre_saisi: centimes (int) valides par le serializer, ou None
    :return: dict pour le template (voir les cles en bas)
    """
    contexte_recharge = {
        "tag_id": carte.tag_id,
        "uuid_pv": str(point_de_vente.uuid) if point_de_vente else "",
        "produits": [],
        "produit_choisi": None,
        "tarifs": [],
        "tarif_choisi": None,
        "montant_a_saisir": False,
        "montant_centimes": None,
        "solde_apres_centimes": None,
        "moyens_paiement": [],
        # Cle d'idempotence du formulaire #card-recharge-form (hx_card_recharge.html).
        # Un double appui sur « Valider » ne recharge qu'une fois.
        # Voir _executer_avec_cle_idempotence().
        # / Idempotency key of #card-recharge-form: a double tap tops up once.
        "cle_idempotence_paiement": uuid_module.uuid4(),
    }

    # Sans point de vente connu, on ne propose pas de recharge.
    # / Without a known POS, no top-up is offered.
    if point_de_vente is None:
        return contexte_recharge

    # 1. Les produits de recharge du lieu (utilisables depuis tous les PV).
    # / 1. The venue top-up products (usable from every POS).
    produits_de_recharge = _produits_de_recharge_du_lieu()

    produit_choisi_en_base = None
    for produit in produits_de_recharge:
        if not produit.prix_euros:
            continue
        est_le_produit_choisi = str(produit.uuid) == uuid_produit_choisi
        if est_le_produit_choisi:
            produit_choisi_en_base = produit
        contexte_recharge["produits"].append(
            {
                "uuid": str(produit.uuid),
                # Le nom de la monnaie suffit : le titre de la zone dit deja « Recharger »
                # / The currency name is enough: the zone title already says "Top up"
                "nom": produit.asset.name,
                "icone": ICONES_RECHARGE.get(produit.methode_caisse, "coins"),
                "est_offert": produit.methode_caisse in METHODES_RECHARGE_GRATUITES,
                "est_choisi": est_le_produit_choisi,
            }
        )

    if produit_choisi_en_base is None:
        return contexte_recharge

    produit_est_offert = produit_choisi_en_base.methode_caisse in METHODES_RECHARGE_GRATUITES
    contexte_recharge["produit_choisi"] = {
        "uuid": str(produit_choisi_en_base.uuid),
        "nom": produit_choisi_en_base.asset.name,
        "est_offert": produit_est_offert,
    }

    # 2. Les tarifs du produit choisi
    # / 2. The chosen product's prices
    tarif_choisi_en_base = None
    for tarif in produit_choisi_en_base.prix_euros:
        if str(tarif.uuid) == uuid_prix_choisi:
            tarif_choisi_en_base = tarif
        contexte_recharge["tarifs"].append(
            {
                "uuid": str(tarif.uuid),
                "prix_euros": tarif.prix,
                "est_libre": tarif.free_price,
            }
        )

    if tarif_choisi_en_base is None:
        return contexte_recharge

    contexte_recharge["tarif_choisi"] = {
        "uuid": str(tarif_choisi_en_base.uuid),
        "est_libre": tarif_choisi_en_base.free_price,
        "minimum_euros": tarif_choisi_en_base.prix,
    }

    # 3. Le montant : le prix du tarif, ou le montant libre saisi.
    # / 3. The amount: the price, or the typed free amount.
    if tarif_choisi_en_base.free_price:
        if montant_libre_saisi is None:
            contexte_recharge["montant_a_saisir"] = True
            return contexte_recharge
        montant_centimes = montant_libre_saisi
    else:
        montant_centimes = int(round(tarif_choisi_en_base.prix * 100))

    contexte_recharge["montant_centimes"] = montant_centimes

    # 4. Le solde de CETTE monnaie apres la recharge (base locale, pas de Fedow distant)
    # / 4. The balance of THIS currency after the top-up (local DB, no remote Fedow)
    wallet_de_la_carte = _obtenir_ou_creer_wallet(carte)
    solde_actuel_centimes = WalletService.obtenir_solde(
        wallet_de_la_carte, produit_choisi_en_base.asset
    )
    contexte_recharge["solde_apres_centimes"] = solde_actuel_centimes + montant_centimes

    # Les moyens de paiement d'une recharge payante : ceux du point de vente,
    # sans le cashless (regle de _determiner_moyens_paiement pour RE).
    # / Payment methods for a paid top-up: the POS ones, without cashless.
    if not produit_est_offert:
        article_recharge = {
            "product": produit_choisi_en_base,
            "price": tarif_choisi_en_base,
            "quantite": 1,
        }
        contexte_recharge["moyens_paiement"] = _determiner_moyens_paiement(
            point_de_vente, [article_recharge]
        )

    return contexte_recharge


def _panier_contient_recharges(articles_panier):
    """
    Vérifie si le panier contient au moins un article de recharge (RE/RC/TM).
    Checks if the cart contains at least one top-up article (RE/RC/TM).

    LOCALISATION : laboutik/views.py

    :param articles_panier: liste de dicts retournée par _extraire_articles_du_panier()
    :return: True si au moins une recharge, False sinon
    """
    for article in articles_panier:
        if article["product"].methode_caisse in METHODES_RECHARGE:
            return True
    return False


def _panier_contient_recharges_payantes(articles_panier):
    """
    Vérifie si le panier contient des recharges euros (RE) qui nécessitent un paiement.
    Les recharges cadeau (RC) et temps (TM) sont gratuites et ne comptent pas.
    / Checks if the cart contains euro top-ups (RE) that require payment.
    Gift (RC) and time (TM) top-ups are free and don't count.

    LOCALISATION : laboutik/views.py

    :param articles_panier: liste de dicts retournée par _extraire_articles_du_panier()
    :return: True si au moins une recharge payante (RE), False sinon
    """
    for article in articles_panier:
        if article["product"].methode_caisse in METHODES_RECHARGE_PAYANTES:
            return True
    return False


def _tarif_est_en_points(tarif):
    """
    Le tarif est-il en points ou en temps ?
    / Is the price in points or time?

    LOCALISATION : laboutik/views.py

    Oui s'il porte une monnaie (`asset`, FID ou TIM) OU s'il est coche « non
    fiduciaire ». Un tarif coche sans monnaie n'est donc jamais pris pour un
    tarif en euros.
    / Yes if it carries a currency OR is marked non-fiduciary.

    :param tarif: Price
    :return: bool
    """
    return tarif.asset_id is not None or tarif.non_fiduciaire


def _panier_est_en_points(articles_panier):
    """
    Le panier contient-il au moins un tarif en points ou en temps ?
    / Does the cart hold at least one points or time price?

    LOCALISATION : laboutik/views.py

    Un tarif en points porte sa monnaie (`price.asset`, FID ou TIM). Un tarif en
    euros n'en porte pas.
    Ne leve jamais d'erreur : le melange de monnaies est refuse par
    _monnaie_du_panier(), appelee par les gardes de paiement.
    / Never raises: mixed currencies are refused by _monnaie_du_panier().

    :param articles_panier: liste de dicts de _extraire_articles_du_panier()
    :return: bool
    """
    for article in articles_panier:
        if _tarif_est_en_points(article["price"]):
            return True
    return False


def _monnaie_du_panier(articles_panier):
    """
    La monnaie non monetaire du panier, ou None pour un panier en euros.
    / The cart's non-monetary currency, or None for a euro cart.

    LOCALISATION : laboutik/views.py

    Un panier ne contient qu'une monnaie : uniquement des euros, OU uniquement
    UNE monnaie de points ou de temps. Additionner des points et des euros (ou
    des points et des heures) n'aurait pas de sens.

    Appelee par / Called by : moyens_paiement(), _executer_paiement().

    :param articles_panier: liste de dicts de _extraire_articles_du_panier()
    :return: Asset (FID ou TIM), ou None
    :raises ValueError: le panier melange plusieurs monnaies (message pour le caissier)
    """
    monnaies_du_panier = set()
    for article in articles_panier:
        monnaies_du_panier.add(article["price"].asset)

    if len(monnaies_du_panier) > 1:
        raise ValueError(
            _(
                "Un panier ne mélange pas plusieurs monnaies : "
                "encaissez-les séparément."
            )
        )
    if not monnaies_du_panier:
        return None
    return monnaies_du_panier.pop()


def _currency_data_du_panier(articles_panier):
    """
    L'unite des montants d'un ecran de paiement : l'euro, ou la monnaie de points
    ou de temps du panier (« 300,00 Points fidélité »).
    / The amount unit of a payment screen: euro, or the cart's points currency.

    LOCALISATION : laboutik/views.py

    Meme forme que CURRENCY_DATA : les gabarits lisent `currency_data.symbol`.
    Un panier melange (refuse par les gardes de paiement) garde l'euro.
    / Same shape as CURRENCY_DATA. A mixed cart (refused by the guards) keeps euro.

    :param articles_panier: liste de dicts de _extraire_articles_du_panier()
    :return: dict {"cc", "symbol", "name"}
    """
    try:
        monnaie_du_panier = _monnaie_du_panier(articles_panier)
    except ValueError:
        return CURRENCY_DATA
    if monnaie_du_panier is None:
        return CURRENCY_DATA
    return {
        "cc": monnaie_du_panier.currency_code,
        "symbol": monnaie_du_panier.name,
        "name": monnaie_du_panier.name,
    }


def _panier_peut_etre_offert(articles_panier, tag_id_carte_manager):
    """
    Le panier peut-il etre offert (tuile et paiement OFFRIR) ?
    / Can the cart be gifted (GIFT tile and payment)?

    LOCALISATION : laboutik/views.py

    Oui si la carte primaire du caissier est en mode gerant, LU EN BASE
    (CartePrimaire.edit_mode), jamais une valeur envoyee par le navigateur.
    Non, meme en mode gerant, pour :
    - un retour de consigne : c'est un remboursement, pas une vente ;
    - une recharge en euros : offrir creerait de la monnaie locale remboursable ;
    - un panier en points ou en temps : il se paie uniquement par carte NFC.
    / Yes when the cashier's primary card is in manager mode (read from the
    database). Never for a deposit return, a euro top-up or a points cart.

    Appelee par / Called by : moyens_paiement(), _rendre_popup_paiement_client_identifie(),
    _executer_paiement() (garde serveur / server guard).

    :param articles_panier: liste de dicts de _extraire_articles_du_panier()
    :param tag_id_carte_manager: tag de la carte primaire (POST « tag_id_cm »)
    :return: bool
    """
    if not tag_id_carte_manager:
        return False
    carte_primaire_obj, erreur = _charger_carte_primaire(tag_id_carte_manager)
    if erreur is not None or not carte_primaire_obj.edit_mode:
        return False
    if _panier_contient_retour_consigne(articles_panier):
        return False
    if _panier_contient_recharges_payantes(articles_panier):
        return False
    if _panier_est_en_points(articles_panier):
        return False
    return True


def _panier_contient_retour_consigne(articles_panier):
    """
    Vérifie si le panier contient au moins un retour de consigne (CR).
    / Checks if the cart contains at least one deposit return (CR).

    LOCALISATION : laboutik/views.py

    Un retour de consigne rend de l'argent au client : son prix est NEGATIF.
    C'est la seule opération du comptoir qui va dans ce sens, et elle change le
    comportement de tout l'écran de paiement (moyens proposés, total en valeur
    absolue, libellés). D'où ce test, fait une fois et partagé.
    / A deposit return gives money back: its price is NEGATIVE. It changes the whole
      payment screen, hence this shared test.

    :param articles_panier: liste de dicts retournée par _extraire_articles_du_panier()
    :return: True si au moins un retour de consigne, False sinon
    """
    for article in articles_panier:
        if article["product"].methode_caisse == Product.RETOUR_CONSIGNE:
            return True
    return False


def _panier_est_uniquement_retour_consigne(articles_panier):
    """
    Vérifie que TOUS les articles du panier sont des retours de consigne.
    / Checks that EVERY article in the cart is a deposit return.

    LOCALISATION : laboutik/views.py

    Sert à refuser les paniers mélangés. Le total d'un panier qui porte une consigne
    est affiché en valeur absolue : sur un panier mélangé (une bière à 3 € et un
    retour à -1 €), le total vaut 2 € et l'écran annoncerait « à rembourser 2 € »
    alors que le client DOIT 2 €. La valeur absolue n'a de sens que si le panier est
    entièrement négatif.
    / Used to refuse mixed carts: abs() on the total only makes sense when the whole
      cart is negative.

    :param articles_panier: liste de dicts retournée par _extraire_articles_du_panier()
    :return: True si le panier est non vide et entièrement composé de retours (CR)
    """
    if not articles_panier:
        return False
    for article in articles_panier:
        if article["product"].methode_caisse != Product.RETOUR_CONSIGNE:
            return False
    return True


def _asset_de_retour_consigne(articles_panier):
    """
    Détermine la monnaie à créditer pour un panier de retours de consigne.
    / Determines the currency to credit for a cart of deposit returns.

    LOCALISATION : laboutik/views.py

    Un seul endroit décide, et deux appelants s'en servent : l'écran qui propose (ou
    non) le bouton CASHLESS, et le paiement qui refuse. Les séparer les ferait diverger,
    et le caissier verrait un bouton menant à un refus certain.
    / One place decides, two callers use it: the screen that offers the CASHLESS button
      and the payment that refuses. Splitting them would let them drift apart.

    Trois raisons de ne pas pouvoir créditer :
    - le produit ne désigne aucune monnaie (`Product.asset` vide) ;
    - cette monnaie n'est pas locale : un asset cadeau rendrait au client une monnaie
      offerte par le lieu, à la place de la somme qu'il avait avancée ;
    - le panier porte plusieurs monnaies : le crédit vise un seul asset pour le total.

    :param articles_panier: liste de dicts, tous des retours de consigne
    :return: tuple (asset ou None, message d'erreur traduit ou None)
    """
    if not articles_panier:
        return None, _("Panier vide.")

    asset_a_crediter = articles_panier[0]["product"].asset

    if asset_a_crediter is None:
        return None, _(
            "Ce retour de consigne n'a pas de monnaie associée. Prévenez le gestionnaire."
        )

    if asset_a_crediter.category != Asset.TLF:
        return None, _("Un retour de consigne se rembourse en monnaie locale.")

    for article in articles_panier:
        if article["product"].asset_id != asset_a_crediter.uuid:
            return None, _(
                "Ces retours de consigne portent sur des monnaies différentes. "
                "Rendez-les séparément."
            )

    return asset_a_crediter, None


def _tarifs_en_euros_vendables_a_la_caisse(produit):
    """
    Les tarifs EN EUROS d'un produit que la caisse sait vendre, dans l'ordre de la
    caisse (`_tarifs_vendables_a_la_caisse`). Sans les tarifs en points ou en temps.
    / The EURO prices of a product the POS can sell, in POS order.

    LOCALISATION : laboutik/views.py

    Le prix d'un retour de consigne est le premier de ces tarifs, pris sur le gobelet
    relié. L'admin des produits de caisse refuse un retour relié à un gobelet qui n'en a
    aucun : la caisse et l'admin lisent donc la même règle, ici.
    / A deposit return's price is the first of these prices, on the linked cup. The POS
    product admin refuses a return linked to a cup without any: one shared rule.

    Appelée par / Called by : _prix_de_la_consigne_remboursee_en_centimes(),
    Administration/admin/products.py POSProductForm.clean().

    :param produit: Product
    :return: QuerySet de Price
    """
    return _tarifs_vendables_a_la_caisse().filter(
        product=produit,
        asset__isnull=True,
        non_fiduciaire=False,
    )


def _prix_de_la_consigne_remboursee_en_centimes(produit_de_retour):
    """
    Le prix d'un retour de consigne, en centimes, NÉGATIF : l'opposé du prix du produit
    consigne qu'il rembourse (`Product.consigne_remboursee`, le gobelet vendu).
    / The price of a deposit return, in cents, NEGATIVE: minus the sold cup's price.

    LOCALISATION : laboutik/views.py

    Le prix propre du produit « Retour de consigne » n'est jamais utilisé (D11) : la
    tuile, le total de la caisse, les espèces rendues et le recrédit de la carte
    prennent tous le prix du gobelet. Le retour
    annule ainsi exactement la vente du gobelet.
    Le prix du gobelet est son premier tarif en euros vendable à la caisse, lu comme la
    tuile du gobelet le lit (`_tarifs_vendables_a_la_caisse`, les euros d'abord).
    / The return product's own price is never used: tile, total, cash and card
    re-credit all take the cup's price (its first POS-sellable euro price).

    Appelée par / Called by : _construire_donnees_articles() (tuile),
    _extraire_articles_du_panier() (prix du panier, calculé par le serveur).

    :param produit_de_retour: Product de méthode de caisse RETOUR_CONSIGNE
    :return: int, centimes, négatif
    :raises ValueError: aucune consigne reliée, ou consigne sans tarif en euros
        (message traduit, lisible par le caissier)
    """
    produit_de_la_consigne = produit_de_retour.consigne_remboursee
    if produit_de_la_consigne is None:
        raise ValueError(
            _(
                "Le retour « %(nom)s » ne dit pas quelle consigne il rembourse. "
                "Prévenez le gestionnaire : il faut le relier au produit consigne "
                "dans l'administration."
            )
            % {"nom": produit_de_retour.name}
        )

    tarif_en_euros_de_la_consigne = _tarifs_en_euros_vendables_a_la_caisse(
        produit_de_la_consigne
    ).first()
    if tarif_en_euros_de_la_consigne is None:
        raise ValueError(
            _(
                "La consigne « %(nom)s » n'a pas de tarif en euros : "
                "le retour ne peut pas être remboursé. Prévenez le gestionnaire."
            )
            % {"nom": produit_de_la_consigne.name}
        )

    # Conversion euros → centimes par Decimal, arrondie au demi supérieur : le prix
    # est déjà au centime, l'arrondi ne fait que produire un entier exact.
    # / Euros → cents through Decimal; the price is already whole cents.
    prix_de_la_consigne_en_centimes = int(
        (Decimal(tarif_en_euros_de_la_consigne.prix) * 100).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    return -prix_de_la_consigne_en_centimes


def _panier_contient_uniquement_recharges_gratuites(articles_panier):
    """
    Vérifie si le panier ne contient QUE des recharges gratuites (RC/TM).
    Pas de ventes normales, pas de recharges euros, pas d'adhesions, pas de billets.
    / Checks if the cart contains ONLY free top-ups (RC/TM).
    No normal sales, no euro top-ups, no memberships, no tickets.

    LOCALISATION : laboutik/views.py

    :param articles_panier: liste de dicts retournée par _extraire_articles_du_panier()
    :return: True si uniquement RC/TM, False sinon
    """
    if not articles_panier:
        return False
    for article in articles_panier:
        if article["product"].methode_caisse not in METHODES_RECHARGE_GRATUITES:
            return False
    return True


def _somme_encaissee_du_panier_en_centimes(articles_panier):
    """
    La somme d'argent que le caissier encaisse pour ce panier (espèces, CB, chèque),
    en centimes, signée : négative pour un retour de consigne (argent rendu).
    / The money the cashier collects for this cart, in cents, signed.

    LOCALISATION : laboutik/views.py

    C'est la somme demandée au client (le total du panier) SANS les recharges cadeau :
    elles sont offertes par le lieu, et le service de vente leur écrit un règlement
    « offert » (FREE). Un panier qui mêle une recharge cadeau à d'autres articles est
    refusé avant d'arriver ici (`_panier_melange_recharge_cadeau_et_autres_articles`).
    Elle devient le montant du règlement espèces / CB / chèque de la vente : un montant
    copié de ce qui est encaissé, pas une somme des lignes écrites.
    / The total asked from the customer, without gift top-ups (offered, FREE payment).

    :param articles_panier: liste de dicts de _extraire_articles_du_panier()
    :return: int
    """
    somme_encaissee_en_centimes = 0
    for article in articles_panier:
        article_est_une_recharge_cadeau = (
            article["product"].methode_caisse in METHODES_RECHARGE_GRATUITES
        )
        if article_est_une_recharge_cadeau:
            continue
        somme_encaissee_en_centimes += article["prix_centimes"] * article["quantite"]
    return somme_encaissee_en_centimes


def _operateur_de_la_caisse(request, tag_id_carte_manager):
    """
    La personne qui encaisse, pour `Vente.operateur` : le titulaire de la carte
    primaire présentée s'il est connu, sinon l'utilisateur connecté à la caisse
    (administrateur du lieu ou terminal).
    / Who collects the money: the primary card holder if known, else the logged-in user.

    LOCALISATION : laboutik/views.py

    :param request: la requête de paiement
    :param tag_id_carte_manager: tag de la carte primaire (POST « tag_id_cm »), ou ""
    :return: TibilletUser ou None
    """
    if tag_id_carte_manager:
        carte_primaire_obj, erreur = _charger_carte_primaire(tag_id_carte_manager)
        carte_primaire_trouvee = erreur is None
        if carte_primaire_trouvee and carte_primaire_obj.carte.user is not None:
            return carte_primaire_obj.carte.user

    if request.user.is_authenticated:
        return request.user
    return None


def _panier_melange_recharge_cadeau_et_autres_articles(articles_panier):
    """
    Le panier contient-il une recharge cadeau (RC) ET au moins un autre article ?
    / Does the cart hold a gift top-up (RC) AND at least one other item?

    LOCALISATION : laboutik/views.py

    Un tel panier est refusé par le serveur : la caisse additionne tous les articles
    pour calculer la somme à payer, cadeau compris, et le client paierait le cadeau. La recharge cadeau se fait à part ; seule,
    elle est créditée sans paiement (`identifier_client`).
    / Such a cart is refused: the register would make the customer pay for the gift.

    Appelée par / Called by : _executer_paiement(), _executer_paiement_complementaire().

    :param articles_panier: liste de dicts de _extraire_articles_du_panier()
    :return: bool
    """
    panier_contient_une_recharge_cadeau = False
    panier_contient_un_autre_article = False
    for article in articles_panier:
        if article["product"].methode_caisse in METHODES_RECHARGE_GRATUITES:
            panier_contient_une_recharge_cadeau = True
        else:
            panier_contient_un_autre_article = True
    return panier_contient_une_recharge_cadeau and panier_contient_un_autre_article


# --------------------------------------------------------------------------- #
#  CaisseViewSet — pages principales                                          #
# --------------------------------------------------------------------------- #


class CaisseViewSet(viewsets.ViewSet):
    """
    Pages principales de la caisse LaBoutik.
    Main pages of the LaBoutik cash register.

    - list()            → page d'attente carte primaire / primary card waiting page
    - carte_primaire()  → validation carte NFC + redirection / NFC card validation + redirect
    - point_de_vente()  → interface POS (service direct, tables, kiosk) / POS interface
    """

    permission_classes = [HasLaBoutikTerminalAccess]

    def list(self, request):
        """
        GET /laboutik/caisse/
        Affiche la page d'attente de la carte primaire (carte du responsable de caisse).
        Displays the primary card waiting page (cash register manager's card).
        """

        # pour le chargement des assets de cordova (plugins)
        type_app = request.GET.get("type_app", "unknown")

        state = _construire_state(user=request.user)
        context = {
            "state": state,
            "stateJson": dumps(state),
            "method": request.method,
            "type_app": type_app,
        }
        return render(request, "laboutik/views/ask_primary_card.html", context)

    @action(
        detail=False,
        methods=["post"],
        url_path="carte_primaire",
        url_name="carte_primaire",
    )
    def carte_primaire(self, request):
        """
        POST /laboutik/caisse/carte_primaire/
        Reçoit le tag NFC scanné, vérifie la carte, et redirige vers le PV.
        Receives the scanned NFC tag, checks the card, and redirects to POS.

        - Carte inconnue → "Carte inconnue" / unknown card
        - Carte non primaire → "Carte non primaire" / not a primary card
        - L'ancien Fedow ne confirme pas la carte → ouverture refusée
          (voir _verifier_carte_primaire_aupres_de_l_ancien_fedow)
          / old Fedow does not confirm the card → opening refused
        - 0 PV visible → "Aucun point de vente configuré" / no visible POS configured
        - 1 PV visible ou plus → redirection vers le premier PV (tri par poid_liste),
          sans écran de choix / redirect to the first POS (sorted by poid_liste)
        """
        # Valider le tag NFC avec le serializer DRF (règle stack-ccc)
        # Validate the NFC tag with DRF serializer (stack-ccc rule)
        serializer = CartePrimaireSerializer(data=request.data)
        if not serializer.is_valid():
            # Extraire le premier message d'erreur pour l'affichage
            # Extract the first error message for display
            premiere_erreur = next(iter(serializer.errors.values()))[0]
            return render(
                request,
                "laboutik/partial/hx_primary_card_message.html",
                {
                    "msg": str(premiere_erreur),
                },
            )

        tag_id_carte_manager = serializer.validated_data["tag_id"]
        logger.debug(f"carte_primaire: tag_id reçu = {tag_id_carte_manager}")

        # TODO: à faire valider par le "serializer" ?
        # "cordova" / "pi" / "desktop"
        type_app = request.POST.get("type_app", "unknown").strip()

        # Chercher la carte primaire depuis le tag NFC
        # Look up the primary card from the NFC tag
        carte_primaire_obj, erreur = _charger_carte_primaire(tag_id_carte_manager)
        if erreur is not None:
            logger.debug(f"carte_primaire: {erreur}")
            return render(
                request,
                "laboutik/partial/hx_primary_card_message.html",
                {
                    "msg": erreur,
                },
            )

        # L'ancien Fedow fait autorité : il confirme que la carte est encore primaire
        # pour ce lieu. Sinon la caisse ne s'ouvre pas (et la carte primaire locale est
        # supprimée si l'ancien Fedow l'a retirée).
        # / The old Fedow is authoritative: it confirms the card is still primary here.
        erreur_de_l_ancien_fedow = _verifier_carte_primaire_aupres_de_l_ancien_fedow(
            carte_primaire_obj
        )
        if erreur_de_l_ancien_fedow is not None:
            return render(
                request,
                "laboutik/partial/hx_primary_card_message.html",
                {
                    "msg": erreur_de_l_ancien_fedow,
                },
            )

        # Points de vente accessibles (non masqués) — évalué une seule fois
        # Accessible points of sale (not hidden) — evaluated once
        pvs = list(
            carte_primaire_obj.points_de_vente.filter(hidden=False).order_by(
                "poid_liste"
            )
        )
        nombre_de_pvs = len(pvs)

        if nombre_de_pvs == 0:
            logger.debug("carte_primaire: Aucun PV configuré")
            return render(
                request,
                "laboutik/partial/hx_primary_card_message.html",
                {
                    "msg": _("Aucun point de vente configuré"),
                },
            )

        # Toujours rediriger vers le premier PV de la liste (tri par poid_liste).
        # Comportement original de LaBoutik : pas de page de choix intermediaire.
        # Always redirect to the first POS in the list (sorted by poid_liste).
        pv = pvs[0]
        url_point_de_vente = reverse("laboutik-caisse-point_de_vente")
        request.session["client_id"] = 123
        url_avec_params = (
            f"{url_point_de_vente}?uuid_pv={pv.uuid}&tag_id_cm={tag_id_carte_manager}&type_app={type_app}"
        )
        logger.debug(f"carte_primaire: Redirection vers {url_avec_params}")
        return HttpResponseClientRedirect(url_avec_params)

    @action(
        detail=False,
        methods=["get"],
        url_path="point_de_vente",
        url_name="point_de_vente",
    )
    def point_de_vente(self, request):
        """
        GET /laboutik/caisse/point_de_vente/
        Affiche l'interface POS selon le mode du point de vente.
        Displays the POS interface depending on the point of sale mode.

        Modes possibles / Possible modes :
        - Service direct → interface de vente immédiate / immediate sales interface
        - Tables (restaurant) → choix de table puis commande / table selection then order
        - Kiosk → interface borne libre-service / self-service kiosk interface
        """
        uuid_pv = request.GET.get("uuid_pv")
        tag_id_carte_manager = request.GET.get("tag_id_cm")
        type_app = request.GET.get("type_app", "unknown")

        # Récupérer l'UUID de table (mode restaurant uniquement)
        # Get the table UUID (restaurant mode only)
        id_table = request.GET.get("id_table") or None

        # Le paramètre force_service_direct permet de court-circuiter le mode tables
        # The force_service_direct parameter bypasses table mode
        force_service_direct = request.GET.get("force_service_direct") == "true"

        # --- Charger le point de vente depuis la DB ---
        # --- Load the point of sale from DB ---
        try:
            pv = PointDeVente.objects.get(uuid=uuid_pv)
        except (PointDeVente.DoesNotExist, ValueError):
            raise Http404(_("Point de vente introuvable"))

        # --- Vérifier que la carte primaire a accès au PV ---
        # --- Check that the primary card has access to the PV ---
        _valider_carte_primaire_pour_pv(tag_id_carte_manager, uuid_pv)

        # --- Charger la carte primaire (opérateur de caisse) ---
        # --- Load the primary card (POS operator) ---
        carte_primaire_obj = None
        pvs_list = []
        if tag_id_carte_manager:
            carte_primaire_obj, _erreur = _charger_carte_primaire(tag_id_carte_manager)
            if carte_primaire_obj is not None:
                pvs_list = list(
                    carte_primaire_obj.points_de_vente.filter(hidden=False)
                    .order_by("poid_liste")
                    .values_list("uuid", "name", "poid_liste", "icon")
                )

        # --- Pré-charger les events billetterie en 3 requêtes max ---
        # --- Pre-load billetterie events in max 3 queries ---
        events_billetterie = None
        if pv.comportement == PointDeVente.BILLETTERIE:
            events_billetterie = _charger_events_billetterie()

        # --- Construire les données articles et catégories ---
        # --- Build article and category data ---
        articles = _construire_donnees_articles(
            pv, events_billetterie=events_billetterie
        )
        categories = _construire_donnees_categories(
            pv, events_billetterie=events_billetterie
        )

        # --- Construire le state (enrichi avec PV + carte primaire) ---
        # --- Build state (enriched with POS + primary card) ---
        state = _construire_state(pv, carte_primaire_obj, user=request.user)

        # --- Choisir le template selon le mode du point de vente ---
        # --- Choose the template based on the point of sale mode ---

        # Par défaut : mode restaurant → afficher le choix des tables
        # Default: restaurant mode → show table selection
        titre_page = _("Resto")
        template_name = "laboutik/views/restaurant_interface.html"

        # Service direct (pas de tables) → interface de vente directe
        # Direct service (no tables) → direct sales interface
        if pv.service_direct or force_service_direct:
            titre_page = _("Service direct")
            template_name = "laboutik/views/common_user_interface.html"

        # Une table spécifique est sélectionnée → interface de commande
        # A specific table is selected → order interface
        if id_table is not None:
            try:
                table_obj = Table.objects.get(uuid=id_table)
                nom_table = table_obj.name
            except (Table.DoesNotExist, ValueError):
                nom_table = str(id_table)
            titre_page = _("Commande table ") + nom_table
            template_name = "laboutik/views/common_user_interface.html"

        # --- Construire le dict PV au format attendu par les templates ---
        # --- Build POS dict in the format expected by templates ---
        pv_dict = {
            "id": str(pv.uuid),
            "name": pv.name,
            "icon": pv.icon or "",
            "comportement": pv.comportement,
            "service_direct": pv.service_direct,
            "afficher_les_prix": pv.afficher_les_prix,
            "articles": articles,
        }

        # --- Construire le dict carte au format attendu par les templates ---
        # --- Build card dict in the format expected by templates ---
        card_dict = {
            "tag_id": tag_id_carte_manager or "",
            "name": str(
                carte_primaire_obj.carte.number or carte_primaire_obj.carte.tag_id
            )
            if carte_primaire_obj
            else "",
            "mode_gerant": carte_primaire_obj.edit_mode
            if carte_primaire_obj
            else False,
            "pvs_list": [
                {
                    "uuid": str(uuid),
                    "name": name,
                    "poid_liste": poid,
                    "icon": icon or "",
                }
                for uuid, name, poid, icon in pvs_list
            ],
        }

        # --- Tables (mode restaurant) ---
        # --- Tables (restaurant mode) ---
        tables_list = []
        if pv.accepte_commandes:
            tables_qs = Table.objects.filter(archive=False).order_by("poids", "name")
            for table in tables_qs:
                tables_list.append(
                    {
                        "id": str(table.uuid),
                        "name": table.name,
                        "statut": table.statut,
                    }
                )

        # Couleurs de statut des tables (mode restaurant)
        # Table status colors (restaurant mode) :
        #   "S" = Servie (served) → orange
        #   "O" = Occupée (occupied) → rouge / red
        #   "L" = Libre (free) → vert / green
        couleurs_statut_tables = {
            "S": "--orange01",
            "O": "--rouge01",
            "L": "--vert02",
        }

        # Configuration globale de l'interface caisse (singleton, get_or_create)
        # Global POS interface configuration (singleton, get_or_create)
        laboutik_config = LaboutikConfiguration.get_solo()

        context = {
            "hostname_client": "",
            "state": state,
            "stateJson": dumps(state),
            # "pv" et "card" : noms courts imposés par les templates cotton et JS existants
            # "pv" and "card": short names required by existing cotton templates and JS
            "pv": pv_dict,
            "card": card_dict,
            "categories": categories,
            "categoriy_angry": CATEGORIE_PAR_DEFAUT,
            "tables": tables_list,
            "table_status_colors": couleurs_statut_tables,
            "title": titre_page,
            "currency_data": CURRENCY_DATA,
            # UUID de l'article "paiement fractionné" — permet de scinder un paiement
            # UUID of the "split payment" article — allows splitting a payment
            "uuidArticlePaiementFractionne": "42ffe511-d880-4964-9b96-0981a9fe4071",
            "id_table": id_table,
            "laboutik_config": laboutik_config,
            # Mode ecole : active le bandeau SIMULATION dans header.html (LNE exigence 5)
            # / Training mode: enables SIMULATION banner in header.html (LNE req. 5)
            "mode_ecole": laboutik_config.mode_ecole,
            # Version du logiciel pour le footer (LNE exigence 21)
            # / Software version for the footer (LNE requirement 21)
            "version_logiciel": _lire_version(),
            # Pour l'injection conditionnelle de cordova.js afin de récupérer les plugin
            "type_app": type_app,
        }
        return render(request, template_name, context)


    # ----------------------------------------------------------------------- #
    # Interface direct pour gèrer le contenu d'une carte cashless             #
    # ----------------------------------------------------------------------- #
    @action(
        detail=False,
        methods=["get"],
        url_path="managed_card",
        url_name="managed_card",
    )
    def managed_card(self, request):
        uuid_pv = request.GET.get("uuid_pv") or None

        # --- Charger le point de vente depuis la DB ---
        # --- Load the point of sale from DB ---
        try:
            pv = PointDeVente.objects.get(uuid=uuid_pv)
            state = _construire_state(pv, user=request.user)
        except (PointDeVente.DoesNotExist, ValueError):
            raise Http404(_("Point de vente introuvable"))

        # logger.info("-----------------------------------------------------")
        # logger.info(f"pv = {vars(pv)}")
        
        template_name = 'laboutik/partial/hx_managed_card.html'
        list_payment = []
        if state["accepte_especes"]:
            list_payment.append({
                "name": "espece",
                "trad": _("espèce")
            })
        if state["accepte_carte_bancaire"]:
            list_payment.append({
                "name": "carte_bancaire",
                "trad": _("carte bancaire")
            })
        if state["accepte_cheque"]:
            list_payment.append({
                "name": "CH",
                "trad": _("chèque")
            })

        context = {
            "list_payment": list_payment,
            "state": state
        }
        return render(request, template_name, context)


    # ----------------------------------------------------------------------- #
    #  Cloture de caisse (Phase 5)                                             #
    #  Cash register closure (Phase 5)                                         #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["post"], url_path="cloturer", url_name="cloturer")
    def cloturer(self, request):
        """
        POST /laboutik/caisse/cloturer/
        Le « Z de fin de service » : cree la cloture journaliere unique du lieu (la J,
        `comptabilite.ClotureCaisse`), puis annule les commandes de table ouvertes et
        libere les tables, imprime le ticket Z et affiche l'ecran du Z.
        / The end-of-service Z: creates the venue's single daily closure (J), cancels
        open table orders, frees the tables, prints the Z ticket, shows the Z screen.

        LOCALISATION : laboutik/views.py

        FLUX :
        1. Validation (point de vente, carte primaire).
        2. `comptabilite.tasks.creer_la_cloture_journaliere_de_la_caisse` : la J, avec
           l'operateur et le point de vente. Rien a cloturer (aucune vente reglee
           depuis la derniere J) : 400, aucun autre effet.
        3. Les deux effets du bouton : commandes ouvertes annulees, tables libres.
        4. Les demandes au broker, chacune protegee (un echec est journalise) : le
           ticket Z, sur l'imprimante du terminal, trace (type CLOT, lien vers la J) ;
           l'e-mail automatique de la J, si le lieu l'a regle.
        5. L'ecran du Z : l'essentiel du rapport stocke dans la J.
        """
        # --- 1. Valider les donnees (uuid_pv uniquement) ---
        # --- 1. Validate input (uuid_pv only) ---
        serializer = ClotureSerializer(data=request.data)
        if not serializer.is_valid():
            premiere_erreur = next(iter(serializer.errors.values()))[0]
            context_erreur = {
                "msg_type": "warning",
                "msg_content": str(premiere_erreur),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        uuid_pv = serializer.validated_data["uuid_pv"]

        # --- 2. Verifier que la carte primaire a acces au PV ---
        # --- 2. Check that the primary card has access to the PV ---
        tag_id_carte_manager = request.POST.get("tag_id_cm", "")
        _valider_carte_primaire_pour_pv(tag_id_carte_manager, uuid_pv)

        # --- 3. Charger le point de vente ---
        # --- 3. Load the point of sale ---
        try:
            point_de_vente = PointDeVente.objects.get(uuid=uuid_pv)
        except PointDeVente.DoesNotExist:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Point de vente introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=404
            )

        # --- 4. La J unique du lieu ---
        # HORS de toute transaction : la creation de la J prend le verrou des ventes
        # dans une transaction courte et DURABLE (`atomic(durable=True)`). Ne jamais
        # entourer cet appel d'un `atomic()` : il leverait RuntimeError.
        # / 4. The venue's single J. OUTSIDE any transaction: never wrap this call in
        #   atomic() (durable step inside).
        operateur = request.user if request.user.is_authenticated else None
        cloture = creer_la_cloture_journaliere_de_la_caisse(
            responsable=operateur,
            point_de_vente=point_de_vente,
        )

        # Rien a cloturer : aucune vente reglee depuis la derniere J (ou aucune
        # vente). Aucune cloture vide, aucun autre effet.
        # / Nothing to close: no settled sale since the last J. No empty closure.
        if cloture is None:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Aucune vente à clôturer"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # --- 5. Fermer les tables ouvertes (OCCUPEE ou SERVIE → LIBRE) ---
        # --- 5. Close open tables (OCCUPIED or SERVED → FREE) ---
        Table.objects.filter(
            statut__in=[Table.OCCUPEE, Table.SERVIE],
        ).update(statut=Table.LIBRE)

        # --- Annuler les commandes encore ouvertes ---
        # --- Cancel still-open orders ---
        CommandeSauvegarde.objects.filter(
            statut=CommandeSauvegarde.OPEN,
        ).update(statut=CommandeSauvegarde.CANCEL)

        # --- 6. Imprimer le Ticket Z sur l'imprimante du terminal qui cloture ---
        #
        # La cloture est GLOBALE au lieu (elle couvre tous les points de vente), mais son
        # ticket sort sur l'imprimante de l'appareil qui la declenche : c'est l'operateur
        # qui est devant, c'est lui qui doit recuperer le papier.
        # / The closure is GLOBAL to the venue, but its ticket prints on the printer of the
        # device that triggered it: the operator is standing right there.
        # Chaque impression d'un Z est tracee (LNE exigence 9) : la tache d'impression
        # ecrit un `ImpressionLog` lie a la J, et marque DUPLICATA une 2e impression.
        # / Every Z print is logged, linked to the J; a 2nd print is a DUPLICATE.
        #
        # Les demandes au broker (impression, e-mail) viennent APRES les effets du
        # bouton, et chacune est protegee : un broker tombe est journalise, la J et
        # l'ecran du Z restent (la J est deja enregistree).
        # / Broker requests come AFTER the button's effects, each one protected: a
        #   broker failure is logged, the J and the Z screen remain.
        # La mise en forme du ticket est dans le meme `try` que la demande
        # d'impression : un rapport illisible par le formatage ne casse pas l'ecran
        # du Z, la J est deja enregistree.
        # / Formatting is in the same `try` as the print request: a formatting
        # error does not break the Z screen, the J is already saved.
        printer_de_ce_terminal = imprimante_du_terminal(request.user)
        if printer_de_ce_terminal:
            try:
                ticket_z_data = formatter_ticket_cloture(cloture)
                ticket_z_data["impression_meta"] = {
                    "uuid_transaction": None,
                    "cloture_uuid": str(cloture.uuid),
                    "type_justificatif": ImpressionLog.CLOTURE,
                    "operateur_pk": str(operateur.pk) if operateur else None,
                    "format_emission": "P",
                }
                imprimer_async.delay(
                    str(printer_de_ce_terminal.pk),
                    ticket_z_data,
                    connection.schema_name,
                )
            except Exception:
                logger.exception(
                    f"[{connection.schema_name}] Échec de la demande d'impression "
                    f"du Z n° {cloture.numero_sequentiel}."
                )

        # L'e-mail automatique de la J, si le lieu l'a regle pour les J.
        # / The J's automatic e-mail, when the venue set it for J.
        try:
            demander_l_email_automatique_si_configure(connection.schema_name, cloture)
        except Exception:
            logger.exception(
                f"[{connection.schema_name}] Échec de la demande d'e-mail "
                f"du Z n° {cloture.numero_sequentiel}."
            )

        # --- 7. Logger / Log ---
        logger.info(
            f"Cloture caisse: PV={point_de_vente.name}, "
            f"J n° {cloture.numero_sequentiel}, total={cloture.total_general}cts, "
            f"perpetuel={cloture.total_perpetuel}cts, "
            f"operations={cloture.nombre_transactions}"
        )

        # --- 8. L'ecran du Z ---
        # L'essentiel du rapport stocke dans la J, mis en forme par
        # `comptabilite/presentation.py` (aucune regle d'affichage recopiee ici) :
        # chiffre d'affaires, reglements, tiroir, phrase de reconciliation. Le Z
        # couvre aussi les ventes en ligne : le reste est sur la fiche de l'admin.
        # / The Z screen: the essential sections of the J's stored report, formatted
        #   by comptabilite/presentation.py; the rest is on the admin page.
        context = _contexte_de_l_ecran_du_z(cloture)
        return render(request, "laboutik/partial/hx_cloture_rapport.html", context)

    # ----------------------------------------------------------------------- #
    #  Export PDF / CSV / Email du rapport de cloture (Phase 5)                #
    #  PDF / CSV / Email export of the closure report (Phase 5)                #
    # ----------------------------------------------------------------------- #

    @action(
        detail=True, methods=["get"], url_path="rapport_pdf", url_name="rapport_pdf"
    )
    def rapport_pdf(self, request, pk=None):
        """
        GET /laboutik/caisse/<uuid>/rapport_pdf/
        Telecharge le PDF de la cloture unique : le meme que celui de l'admin
        (`comptabilite/pdf.py`).
        / Downloads the single closure's PDF, the same as the admin's.

        LOCALISATION : laboutik/views.py
        """
        cloture = get_object_or_404(ClotureCaisseUnique, uuid=pk)
        contenu_du_pdf, nom_du_fichier, type_du_fichier = generer_pdf_cloture(cloture)
        response = HttpResponse(contenu_du_pdf, content_type=type_du_fichier)
        response["Content-Disposition"] = f'attachment; filename="{nom_du_fichier}"'
        return response

    @action(
        detail=True, methods=["get"], url_path="rapport_csv", url_name="rapport_csv"
    )
    def rapport_csv(self, request, pk=None):
        """
        GET /laboutik/caisse/<uuid>/rapport_csv/
        Telecharge le CSV de la cloture unique : le meme que celui de l'admin
        (`comptabilite/csv_export.py`).
        / Downloads the single closure's CSV, the same as the admin's.

        LOCALISATION : laboutik/views.py
        """
        cloture = get_object_or_404(ClotureCaisseUnique, uuid=pk)
        contenu_du_csv, nom_du_fichier, type_du_fichier = generer_csv_cloture(cloture)
        response = HttpResponse(contenu_du_csv, content_type=type_du_fichier)
        response["Content-Disposition"] = f'attachment; filename="{nom_du_fichier}"'
        return response

    @action(
        detail=True,
        methods=["post"],
        url_path="envoyer_rapport",
        url_name="envoyer_rapport",
    )
    def envoyer_rapport(self, request, pk=None):
        """
        POST /laboutik/caisse/<uuid>/envoyer_rapport/
        Envoie l'email de la cloture unique (PDF en piece jointe) aux destinataires
        du lieu (`Configuration.rapport_emails`), quelle que soit la periodicite du
        rapport : c'est un clic explicite. Une adresse postee avec le formulaire est
        ignoree. Sans destinataire : message clair, rien n'est envoye.
        / Sends the single closure's e-mail to the venue's recipients, whatever the
        report periodicity. A posted address is ignored. No recipient: clear message.

        LOCALISATION : laboutik/views.py
        """
        cloture = get_object_or_404(ClotureCaisseUnique, uuid=pk)

        destinataires_du_lieu = Configuration.get_solo().rapport_emails or ""
        if not destinataires_du_lieu.strip():
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _(
                    "Aucun destinataire de rapport n'est configuré pour le lieu."
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # La demande part au broker (Celery). Un broker en panne ne doit pas donner
        # une erreur 500 : l'erreur est journalisée et la caisse le dit en mots.
        # / The request goes to the broker; a broken broker gives a clear message.
        try:
            envoyer_email_cloture_demande.delay(
                connection.schema_name,
                str(cloture.uuid),
            )
        except Exception:
            logger.exception(
                f"[{connection.schema_name}] Échec de la demande d'envoi du rapport "
                f"de la clôture n° {cloture.numero_sequentiel}."
            )
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _(
                    "L'envoi du rapport n'a pas pu être demandé. Réessayez plus tard."
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=503
            )

        context = {
            "msg_type": "info",
            "msg_content": _("Envoi du rapport demandé"),
        }
        return render(request, "laboutik/partial/hx_messages.html", context)

    # ----------------------------------------------------------------------- #
    #  Imprimer Ticket X (consultation temporaire, pas de cloture)             #
    #  Print Ticket X (temporary consultation, no closure)                     #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["post"],
        url_path="imprimer-ticket-x",
        url_name="imprimer_ticket_x",
    )
    def imprimer_ticket_x(self, request):
        """
        POST /laboutik/caisse/imprimer-ticket-x/
        Imprime un Ticket X (instantane du service en cours) sur l'imprimante du PV.
        Le Ticket X n'est pas persiste en base — c'est une consultation temporaire.
        / Prints an X-ticket (snapshot of the current shift) on the POS printer.
        The X-ticket is not persisted in the database — it's a temporary consultation.

        LOCALISATION : laboutik/views.py
        """
        uuid_pv = request.POST.get("uuid_pv", "")

        # Le point de vente n'est plus utilise pour trouver l'imprimante (c'est le
        # terminal qui la porte), mais on continue de valider qu'il existe : un POST
        # qui reference un point de vente inconnu est une requete malformee.
        # / The point of sale no longer carries the printer, but we still validate it
        # exists: a POST referencing an unknown one is a malformed request.
        try:
            PointDeVente.objects.get(uuid=uuid_pv)
        except (PointDeVente.DoesNotExist, ValueError):
            return render(
                request,
                "laboutik/partial/hx_print_feedback.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Point de vente introuvable"),
                },
                status=404,
            )

        # Le ticket X sort sur l'imprimante du terminal qui le demande.
        # / The X-ticket prints on the requesting terminal's printer.
        printer_de_ce_terminal = imprimante_du_terminal(request.user)
        if not printer_de_ce_terminal:
            return render(
                request,
                "laboutik/partial/hx_print_feedback.html",
                {
                    "msg_type": "warning",
                    "msg_content": _(
                        "Aucune imprimante configurée pour ce terminal"
                    ),
                },
                status=400,
            )

        # Calculer le rapport du service en cours / Compute current shift report
        datetime_ouverture = _calculer_datetime_ouverture_service()
        if datetime_ouverture is None:
            return render(
                request,
                "laboutik/partial/hx_print_feedback.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Aucune vente en cours — rien a imprimer"),
                },
                status=400,
            )

        # Le rapport X du service en cours : le rapport des ventes unique, de la fin de
        # la derniere J jusqu'a maintenant, jamais stocke.
        # / The current service X report: the single sales report, never stored.
        rapport_du_service = RapportDesVentes(
            datetime_ouverture, dj_timezone.now()
        ).rapport_x()
        ticket_data = formatter_ticket_x(rapport_du_service, datetime_ouverture)

        # La demande d'impression part au broker (Celery). Un broker en panne ne doit
        # pas donner une erreur 500 : l'erreur est journalisée et la caisse le dit.
        # / The print request goes to the broker; a broken broker gives a message.
        schema_name = connection.schema_name
        try:
            imprimer_async.delay(
                str(printer_de_ce_terminal.pk),
                ticket_data,
                schema_name,
            )
        except Exception:
            logger.exception(
                f"[{schema_name}] Échec de la demande d'impression du ticket X."
            )
            return render(
                request,
                "laboutik/partial/hx_print_feedback.html",
                {
                    "msg_type": "warning",
                    "msg_content": _(
                        "Le ticket X n'a pas pu être envoyé à l'imprimante. "
                        "Réessayez plus tard."
                    ),
                },
                status=503,
            )

        return render(
            request,
            "laboutik/partial/hx_print_feedback.html",
            {
                "msg_type": "success",
                "msg_content": _("Ticket X envoye a l'imprimante"),
            },
        )

    # ----------------------------------------------------------------------- #
    #  Export fiscal — archive ZIP signee HMAC pour l'administration fiscale   #
    #  Fiscal export — HMAC-signed ZIP archive for tax administration          #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["get", "post"],
        url_path="export-fiscal",
        url_name="export_fiscal",
    )
    def export_fiscal(self, request):
        """
        GET /laboutik/caisse/export-fiscal/
        Affiche le formulaire : date de debut obligatoire, date de fin facultative.
        / Shows the form: start date required, end date optional.

        POST /laboutik/caisse/export-fiscal/
        Genere et telecharge l'archive ZIP signee HMAC, sur 365 jours au plus.
        / Generates and downloads the HMAC-signed ZIP archive, 365 days at most.

        LOCALISATION : laboutik/views.py

        FLUX :
        1. GET : affiche le formulaire (template hx_export_fiscal.html)
        2. POST : valide les dates, genere les fichiers, calcule les hash,
           empaquete en ZIP, journalise l'operation, renvoie le ZIP.
        / 1. GET: shows the form
        2. POST: validates dates, generates files, computes hashes,
           packages into ZIP, logs the operation, returns the ZIP.
        """
        from laboutik.archivage import reponse_de_l_export_fiscal

        if request.method == "GET":
            # Detecter si la requete vient de l'admin (HTMX) ou d'un acces direct (POS)
            # Si HTMX : renvoyer le partial admin Unfold (charge dans la card)
            # Si direct : renvoyer la page POS complete
            # / Detect if request comes from admin (HTMX) or direct access (POS)
            est_requete_htmx = request.headers.get("HX-Request") == "true"
            if est_requete_htmx:
                return render(
                    request,
                    "admin/cloture/export_fiscal_form.html",
                    {
                        "form_action_url": request.path,
                        "cancel_url": request.headers.get(
                            "HX-Current-URL", "/admin/laboutik/cloturecaisse/"
                        ),
                    },
                )
            return render(request, "laboutik/partial/hx_export_fiscal.html")

        # --- POST : generation de l'archive ZIP, par la logique commune ---
        # La meme fonction sert l'admin de la comptabilite (comptabilite/admin.py).
        # / POST: ZIP archive generation, through the shared logic (also used by the
        # accounting admin).
        return reponse_de_l_export_fiscal(request)

    # ----------------------------------------------------------------------- #
    #  Export FEC — fichier des ecritures comptables (18 colonnes)              #
    #  FEC export — accounting entries file (18 columns)                        #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["get", "post"],
        url_path="export-fec",
        url_name="export_fec",
    )
    def export_fec(self, request):
        """
        GET /laboutik/caisse/export-fec/
        Affiche le formulaire avec dates debut/fin optionnelles.
        / Shows the form with optional start/end dates.

        POST /laboutik/caisse/export-fec/
        Genere et telecharge le fichier FEC (TSV 18 colonnes).
        / Generates and downloads the FEC file (18-column TSV).

        LOCALISATION : laboutik/views.py
        """
        from datetime import date as date_type

        from django.db import connection
        from django.http import HttpResponse

        from laboutik.fec import generer_fec
        from laboutik.models import ClotureCaisse

        if request.method == "GET":
            # Detecter si la requete vient de l'admin (HTMX) ou d'un acces direct (POS)
            # / Detect if request comes from admin (HTMX) or direct access (POS)
            est_requete_htmx = request.headers.get("HX-Request") == "true"
            if est_requete_htmx:
                return render(
                    request,
                    "admin/cloture/export_fec_form.html",
                    {
                        "form_action_url": request.path,
                        "cancel_url": request.headers.get(
                            "HX-Current-URL", "/admin/laboutik/cloturecaisse/"
                        ),
                    },
                )
            return render(request, "laboutik/partial/hx_export_fiscal.html")

        # --- POST : generation du fichier FEC ---
        # --- POST: FEC file generation ---

        # Parser les dates optionnelles / Parse optional dates
        debut = None
        fin = None
        debut_str = request.POST.get("debut", "").strip()
        fin_str = request.POST.get("fin", "").strip()
        try:
            if debut_str:
                debut = date_type.fromisoformat(debut_str)
            if fin_str:
                fin = date_type.fromisoformat(fin_str)
        except ValueError:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Format de date invalide."),
                },
                status=400,
            )

        # Filtrer les clotures journalieres / Filter daily closures
        clotures = ClotureCaisse.objects.filter(
            niveau=ClotureCaisse.JOURNALIERE
        ).order_by("datetime_cloture")
        if debut:
            clotures = clotures.filter(datetime_cloture__date__gte=debut)
        if fin:
            clotures = clotures.filter(datetime_cloture__date__lte=fin)

        if not clotures.exists():
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _(
                        "Aucune cloture journaliere trouvee pour la periode."
                    ),
                },
                status=404,
            )

        schema = connection.schema_name
        contenu_fec, nom_fichier, avertissements = generer_fec(clotures, schema)

        response = HttpResponse(
            contenu_fec, content_type="text/tab-separated-values; charset=utf-8"
        )
        response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        return response

    # ----------------------------------------------------------------------- #
    #  Export CSV comptable — multi-profils (Sage, EBP, Dolibarr, etc.)       #
    #  CSV accounting export — multi-profile (Sage, EBP, Dolibarr, etc.)      #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["get", "post"],
        url_path="export-csv-comptable",
        url_name="export_csv_comptable",
    )
    def export_csv_comptable(self, request):
        """
        GET /laboutik/caisse/export-csv-comptable/
        Affiche le formulaire avec dates debut/fin + choix de profil.
        / Shows the form with optional start/end dates + profile choice.

        POST /laboutik/caisse/export-csv-comptable/
        Genere et telecharge le fichier CSV comptable.
        / Generates and downloads the accounting CSV file.

        LOCALISATION : laboutik/views.py
        """
        from datetime import date as date_type

        from django.db import connection
        from django.http import HttpResponse

        from laboutik.csv_comptable import generer_csv_comptable
        from laboutik.models import ClotureCaisse
        from laboutik.profils_csv import PROFILS

        if request.method == "GET":
            return render(
                request,
                "admin/cloture/export_csv_comptable_form.html",
                {
                    "form_action_url": request.path,
                    "profils": PROFILS,
                },
            )

        # --- POST : generation du fichier CSV comptable ---
        # --- POST: accounting CSV file generation ---

        # Valider le profil choisi / Validate the chosen profile
        profil_nom = request.POST.get("profil", "").strip()
        if profil_nom not in PROFILS:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Profil inconnu. Choix : %(profils)s")
                    % {
                        "profils": ", ".join(PROFILS.keys()),
                    },
                },
                status=400,
            )

        # Parser les dates optionnelles / Parse optional dates
        debut = None
        fin = None
        debut_str = request.POST.get("debut", "").strip()
        fin_str = request.POST.get("fin", "").strip()
        try:
            if debut_str:
                debut = date_type.fromisoformat(debut_str)
            if fin_str:
                fin = date_type.fromisoformat(fin_str)
        except ValueError:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Format de date invalide."),
                },
                status=400,
            )

        # Filtrer les clotures journalieres / Filter daily closures
        clotures = ClotureCaisse.objects.filter(
            niveau=ClotureCaisse.JOURNALIERE
        ).order_by("datetime_cloture")
        if debut:
            clotures = clotures.filter(datetime_cloture__date__gte=debut)
        if fin:
            clotures = clotures.filter(datetime_cloture__date__lte=fin)

        if not clotures.exists():
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _(
                        "Aucune cloture journaliere trouvee pour la periode."
                    ),
                },
                status=404,
            )

        schema = connection.schema_name
        contenu_bytes, nom_fichier, avertissements = generer_csv_comptable(
            clotures, profil_nom, schema
        )

        profil = PROFILS[profil_nom]
        content_type = "text/csv; charset=" + profil["encodage"]
        response = HttpResponse(contenu_bytes, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        return response

    # ----------------------------------------------------------------------- #
    #  Charger le plan comptable par defaut (ajoute ce qui manque)             #
    #  Load the default chart of accounts (adds what is missing)               #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["post"],
        url_path="charger-plan-comptable",
        url_name="charger_plan_comptable",
    )
    def charger_plan_comptable(self, request):
        """
        POST /laboutik/caisse/charger-plan-comptable/
        Ajoute au lieu ce qui manque du plan comptable par defaut. N'efface rien :
        les comptes existants et les liens des categories restent.
        / Adds to the venue what is missing from the default chart of accounts.
        Erases nothing: existing accounts and category links remain.

        LOCALISATION : laboutik/views.py

        Appele par le bandeau de la liste des comptes de l'admin
        (Administration/templates/admin/comptable/changelist_before.html).
        Le chargement lui-meme : laboutik/plan_comptable.py.
        / Called by the admin accounts list banner. Loading: laboutik/plan_comptable.py.
        """
        from laboutik.models import CompteComptable
        from laboutik.plan_comptable import charger_le_plan_comptable_par_defaut

        nombre_de_comptes_avant = CompteComptable.objects.count()

        try:
            avertissements = charger_le_plan_comptable_par_defaut()
        except Exception as e:
            logger.error(f"Erreur chargement plan comptable : {e}")
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": str(e),
                },
                status=500,
            )

        nombre_de_comptes_ajoutes = (
            CompteComptable.objects.count() - nombre_de_comptes_avant
        )
        message = _(
            "%(nombre)s compte(s) ajouté(s) au plan comptable. Rien n'a été effacé."
        ) % {
            "nombre": nombre_de_comptes_ajoutes,
        }

        # Un avertissement (ex. numero de TVA deja pris) est montre au gestionnaire.
        # / A warning (e.g. VAT number already taken) is shown to the manager.
        type_du_message = "success"
        if avertissements:
            type_du_message = "warning"
            message = f"{message} {' '.join(avertissements)}"

        return render(
            request,
            "laboutik/partial/hx_messages.html",
            {
                "msg_type": type_du_message,
                "msg_content": message,
            },
        )

    # ----------------------------------------------------------------------- #
    #  Fond de caisse — lecture et modification du montant initial              #
    #  Cash float — read and update initial drawer amount                      #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["get", "post"],
        url_path="fond-de-caisse",
        url_name="fond_de_caisse",
    )
    def fond_de_caisse(self, request):
        """
        GET /laboutik/caisse/fond-de-caisse/
        Affiche le montant actuel du fond de caisse.
        / Shows the current cash float amount.

        POST /laboutik/caisse/fond-de-caisse/
        Met a jour le montant du fond de caisse.
        Le montant est recu en euros (decimal) et converti en centimes.
        / Updates the cash float amount.
        Amount is received in euros (decimal) and converted to cents.

        LOCALISATION : laboutik/views.py
        """
        config = LaboutikConfiguration.get_solo()

        if request.method == "POST":
            # Validation via serializer DRF (conversion euros → centimes incluse)
            # / Validation via DRF serializer (euros → cents conversion included)
            from laboutik.serializers import FondDeCaisseSerializer

            serializer = FondDeCaisseSerializer(data=request.POST)
            if not serializer.is_valid():
                premiere_erreur = list(serializer.errors.values())[0][0]
                return render(
                    request,
                    "laboutik/partial/hx_messages.html",
                    {
                        "msg_type": "warning",
                        "msg_content": str(premiere_erreur),
                    },
                    status=400,
                )

            montant_centimes = serializer.validated_data["montant_euros"]

            # Trace du changement de fond de caisse avant modification
            # / Record cash float change before modification
            uuid_pv = request.POST.get("uuid_pv") or request.GET.get("uuid_pv")
            point_de_vente_pour_historique = None
            if uuid_pv:
                point_de_vente_pour_historique = PointDeVente.objects.filter(
                    uuid=uuid_pv
                ).first()

            HistoriqueFondDeCaisse.objects.create(
                ancien_montant=config.fond_de_caisse,
                nouveau_montant=montant_centimes,
                operateur=request.user if request.user.is_authenticated else None,
                point_de_vente=point_de_vente_pour_historique,
            )

            config.fond_de_caisse = montant_centimes
            # save() sans update_fields : django-solo gere l'insert-or-update.
            # update_fields peut echouer si le singleton n'existe pas encore.
            # / save() without update_fields: django-solo handles insert-or-update.
            config.save()

            logger.info(
                f"Fond de caisse mis a jour : {montant_centimes} centimes "
                f"par {request.user}"
            )

        # GET ou POST reussi : afficher le formulaire avec le montant actuel
        # / GET or successful POST: show the form with current amount
        montant_actuel_euros = config.fond_de_caisse / 100

        # Propager les params ventes pour le bouton retour
        # / Propagate sales params for the back button
        uuid_pv = request.GET.get("uuid_pv", request.POST.get("uuid_pv", ""))
        tag_id_cm = request.GET.get("tag_id_cm", request.POST.get("tag_id_cm", ""))
        type_app = request.GET.get("type_app", request.POST.get("type_app", ""))
        params_ventes = _construire_params_ventes(uuid_pv, tag_id_cm, type_app)

        context = {
            "montant_actuel_euros": f"{montant_actuel_euros:.2f}",
            "montant_actuel_centimes": config.fond_de_caisse,
            "message_succes": request.method == "POST",
            "params_ventes": params_ventes,
        }
        return render(request, "laboutik/partial/hx_fond_de_caisse.html", context)

    # ----------------------------------------------------------------------- #
    #  Sortie de caisse — retrait especes avec ventilation par coupure          #
    #  Cash withdrawal — cash removal with denomination breakdown              #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["get"],
        url_path="sortie-de-caisse",
        url_name="sortie_de_caisse",
    )
    def sortie_de_caisse(self, request):
        """
        GET /laboutik/caisse/sortie-de-caisse/
        Affiche le formulaire de sortie de caisse (ventilation par coupure).
        / Shows the cash withdrawal form (denomination breakdown).

        LOCALISATION : laboutik/views.py
        """
        # Recuperer le PV depuis le query param (le menu Ventes le passe)
        # / Get PV from query param (Sales menu passes it)
        uuid_pv = request.GET.get("uuid_pv", "")
        tag_id_cm = request.GET.get("tag_id_cm", "")
        type_app = request.GET.get("type_app", "")
        params_ventes = _construire_params_ventes(uuid_pv, tag_id_cm, type_app)

        # Le tiroir du service en cours : la section « caisse especes » du rapport des
        # ventes unique (la meme que le ticket X et la J), mise en forme par
        # `comptabilite/presentation.py`. Il commence a la fin de la derniere J, meme
        # sans vente depuis (`_section_du_tiroir_du_service_en_cours`).
        # / The current service drawer: the "caisse especes" section of the single
        #   report, formatted by the shared presentation.
        section_du_tiroir = _section_du_tiroir_du_service_en_cours()
        lignes_du_tiroir_a_l_ecran = _lignes_du_tiroir_pour_l_ecran(section_du_tiroir)
        fond_de_caisse_centimes = section_du_tiroir["fond_de_caisse_en_centimes"]
        solde_total_centimes = section_du_tiroir["solde_theorique_en_centimes"]
        # Les especes du service, nettes : tout ce qui est entre et sorti du tiroir
        # depuis la derniere J. Le controle JS du formulaire refuse de sortir plus que
        # fond + especes nettes (= le solde) et previent si la sortie entame le fond.
        # / The service's net cash: the JS check compares withdrawals to it.
        especes_nettes_du_service_centimes = (
            solde_total_centimes - fond_de_caisse_centimes
        )

        context = {
            "uuid_pv": uuid_pv,
            # tag_id_cm et type_app sont renvoyes en champs caches par le formulaire,
            # pour que creer_sortie_de_caisse puisse reconstruire params_ventes.
            # / Sent back as hidden fields so creer_sortie_de_caisse can rebuild params_ventes.
            "tag_id_cm": tag_id_cm,
            "type_app": type_app,
            "coupures": _COUPURES_POUR_TEMPLATE,
            "coupures_paires": _COUPURES_PAIRES_POUR_TEMPLATE,
            "params_ventes": params_ventes,
            # Données pour l'avertissement JS, indicatives : `creer_sortie_de_caisse`
            # ne compare pas la sortie au solde du tiroir.
            # / Data for the JS warning, indicative: the server does not compare the
            # withdrawal with the drawer balance.
            "fond_de_caisse_centimes": fond_de_caisse_centimes,
            "especes_nettes_du_service_centimes": especes_nettes_du_service_centimes,
            # Les lignes du tiroir, deja ecrites par la presentation partagee.
            # / The drawer lines, already written by the shared presentation.
            "lignes_du_tiroir": lignes_du_tiroir_a_l_ecran,
        }
        return render(request, "laboutik/partial/hx_sortie_de_caisse.html", context)

    @action(
        detail=False,
        methods=["post"],
        url_path="creer-sortie-de-caisse",
        url_name="creer_sortie_de_caisse",
    )
    def creer_sortie_de_caisse(self, request):
        """
        POST /laboutik/caisse/creer-sortie-de-caisse/
        Cree une SortieCaisse avec ventilation JSON.
        Le total est recalcule cote serveur (ne jamais faire confiance au JS).
        / Creates a SortieCaisse with JSON denomination breakdown.
        Total is recalculated server-side (never trust JS).

        LOCALISATION : laboutik/views.py
        """
        # URL de retour vers le formulaire de sortie de caisse, conservant uuid_pv
        # et tag_id_cm pour reconstruire le contexte (PV courant + carte manager).
        # Calcule en debut de vue pour etre disponible dans tous les renders d'erreur.
        # / Back URL to the cash withdrawal form, preserving uuid_pv and tag_id_cm.
        # Computed early to be available in all error renders.
        uuid_pv_brut = request.POST.get("uuid_pv", "")
        tag_id_cm_brut = request.POST.get("tag_id_cm", "")
        type_app_brut = request.POST.get("type_app", "")
        params_ventes = _construire_params_ventes(
            uuid_pv_brut, tag_id_cm_brut, type_app_brut
        )
        back_url_form = reverse("laboutik-caisse-sortie_de_caisse")
        if params_ventes:
            back_url_form = f"{back_url_form}?{params_ventes}"

        # Validation du PV et de la note via serializer DRF
        # / Validate POS and note via DRF serializer
        from laboutik.serializers import SortieDeCaisseSerializer

        serializer = SortieDeCaisseSerializer(data=request.POST)
        if not serializer.is_valid():
            premiere_erreur = list(serializer.errors.values())[0][0]
            return render(
                request,
                "laboutik/partial/hx_alerte_ventes_zone.html",
                {
                    "msg_type": "warning",
                    "msg_content": str(premiere_erreur),
                    "back_url": back_url_form,
                },
                status=400,
            )

        uuid_pv = serializer.validated_data["uuid_pv"]
        note = serializer.validated_data.get("note", "").strip()

        # Recuperer le point de vente
        # / Get the point of sale
        try:
            point_de_vente = PointDeVente.objects.get(uuid=uuid_pv)
        except PointDeVente.DoesNotExist:
            return render(
                request,
                "laboutik/partial/hx_alerte_ventes_zone.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Point de vente introuvable"),
                    "back_url": back_url_form,
                },
                status=404,
            )

        # Lire les quantites par coupure et recalculer le total cote serveur
        # / Read quantities per denomination and recalculate total server-side
        ventilation = {}
        montant_total_centimes = 0

        for coupure_centimes, _label in COUPURES_CENTIMES:
            cle_post = f"coupure_{coupure_centimes}"
            quantite_brute = request.POST.get(cle_post, "0")

            try:
                quantite = int(quantite_brute)
            except (ValueError, TypeError):
                quantite = 0

            if quantite < 0:
                quantite = 0

            if quantite > 0:
                ventilation[str(coupure_centimes)] = quantite
                montant_total_centimes += coupure_centimes * quantite

        # Verifier qu'il y a au moins une coupure
        # / Check that at least one denomination is present
        if montant_total_centimes <= 0:
            return render(
                request,
                "laboutik/partial/hx_alerte_ventes_zone.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Aucune coupure saisie"),
                    "back_url": back_url_form,
                },
                status=400,
            )

        # Creer la sortie de caisse
        # / Create the cash withdrawal
        SortieCaisse.objects.create(
            point_de_vente=point_de_vente,
            operateur=request.user if request.user.is_authenticated else None,
            montant_total=montant_total_centimes,
            ventilation=ventilation,
            note=note,
        )

        logger.info(
            f"Sortie de caisse : {montant_total_centimes} centimes "
            f"depuis PV {point_de_vente.name} par {request.user}"
        )

        # params_ventes est deja calcule en debut de vue pour les renders d'erreur ;
        # on le reutilise tel quel pour le bouton retour de l'ecran de succes.
        # / params_ventes is already computed at the top of the view for error renders;
        # we reuse it as-is for the success screen back button.
        montant_euros = f"{montant_total_centimes / 100:.2f}"
        return render(
            request,
            "laboutik/partial/hx_sortie_succes.html",
            {
                "montant_euros": montant_euros,
                "params_ventes": params_ventes,
            },
        )

    # ----------------------------------------------------------------------- #
    #  Menu Ventes — Ticket X + liste des ventes                               #
    #  Sales menu — Ticket X + sales list                                      #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["get"],
        url_path="recap-en-cours",
        url_name="recap_en_cours",
    )
    def recap_en_cours(self, request):
        """
        GET /laboutik/caisse/recap-en-cours/
        Le recapitulatif du service en cours (lecture seule, rien n'est stocke).
        / The current service recap (read-only, nothing stored).

        LOCALISATION : laboutik/views.py

        FLUX :
        1. Debut du service : `_calculer_datetime_ouverture_service` (fin de la
           derniere J). None : « aucune vente depuis la derniere cloture ».
        2. Le rapport X du rapport des ventes unique
           (`RapportDesVentes(debut, maintenant).rapport_x()`), mis en forme par
           `sections_pour_affichage` : toutes ses sections (reglements et detail
           des ventes compris), l'essentiel ouvert, le reste replie, comme dans
           l'admin.
        3. Rend hx_recap_en_cours.html. L'historique de commande (liste des ventes)
           s'ouvre en bas de l'ecran par son bouton (`liste_ventes`).
        / The single report's X sections; the order history opens below.
        """
        datetime_ouverture = _calculer_datetime_ouverture_service()

        # Si aucune vente depuis la derniere cloture, afficher un message
        # / If no sales since last closure, show a message
        if datetime_ouverture is None:
            context = {"aucune_vente": True}
            return _rendre_vue_ventes(
                request, "laboutik/partial/hx_recap_en_cours.html", context
            )

        datetime_fin = dj_timezone.now()

        context = {
            "aucune_vente": False,
            "datetime_ouverture": datetime_ouverture,
            "datetime_fin": datetime_fin,
        }
        rapport_du_service = RapportDesVentes(datetime_ouverture, datetime_fin).rapport_x()
        context.update(_contexte_du_recap_du_service(rapport_du_service))

        return _rendre_vue_ventes(
            request, "laboutik/partial/hx_recap_en_cours.html", context
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="rapport-temps-reel",
        url_name="rapport_temps_reel",
    )
    def rapport_temps_reel(self, request):
        """
        GET /laboutik/caisse/rapport-temps-reel/
        Rapport comptable complet du service en cours (lecture seule).
        Calcule en temps reel depuis la derniere cloture journaliere.
        Pas de creation de ClotureCaisse. Page standalone (nouvel onglet).
        / Full accounting report of the current shift (read-only).
        Computed in real time since the last daily closure.
        No ClotureCaisse created. Standalone page (new tab).

        LOCALISATION : laboutik/views.py

        FLUX :
        1. Calcule datetime_ouverture via _calculer_datetime_ouverture_service()
        2. Instancie RapportComptableService(pv=None, debut, fin=now())
        3. Appelle generer_rapport_complet() (15 sections)
        4. Rend rapport_temps_reel.html (page complete, pas un partial)
        """
        datetime_ouverture = _calculer_datetime_ouverture_service()

        # Si aucune vente depuis la derniere cloture, afficher un message
        # / If no sales since last closure, show a message
        if datetime_ouverture is None:
            return render(
                request,
                "admin/cloture/rapport_temps_reel.html",
                {"aucune_vente": True},
            )

        datetime_fin = dj_timezone.now()
        service = RapportComptableService(None, datetime_ouverture, datetime_fin)
        rapport = service.generer_rapport_complet()
        nombre_de_transactions = service.lignes.count()

        context = {
            "aucune_vente": False,
            "rapport": rapport,
            "datetime_ouverture": datetime_ouverture,
            "datetime_fin": datetime_fin,
            "nb_transactions": nombre_de_transactions,
        }
        return render(
            request,
            "admin/cloture/rapport_temps_reel.html",
            context,
        )

    @action(
        detail=False, methods=["get"], url_path="liste-ventes", url_name="liste_ventes"
    )
    def liste_ventes(self, request):
        """
        GET /laboutik/caisse/liste-ventes/?pv=uuid&moyen=CA&avant=<numero>
        Liste paginee des ventes du service en cours : une ligne par `Vente`.
        Pagination HTMX avec scroll infini (hx-trigger="revealed").
        / Paginated list of the current service's sales: one row per sale.

        LOCALISATION : laboutik/views.py

        FLUX :
        1. Debut du service : `_calculer_datetime_ouverture_service` (None : aucune
           vente en cours).
        2. Les ventes reglees depuis ce debut, faites sur un point de vente du lieu
           (caisse, tireuse), toutes natures ; filtres point de vente et moyen (un
           reglement de ce moyen).
        3. 20 ventes, la plus recente d'abord. La suite (`?avant=<numero>`) lit les
           ventes de numero plus petit que la derniere affichee : une vente encaissee
           pendant le defilement ne decale pas les pages. Chaque ligne est ecrite par
           `lignes_de_la_liste_des_ventes`.
        4. Rend hx_liste_ventes.html (page complete, liste seule ou lignes suivantes).
        / Settled sales on a point of sale since the service start; 20 at a time,
          the next ones by number (`avant`).
        """
        datetime_ouverture = _calculer_datetime_ouverture_service()

        if datetime_ouverture is None:
            context = {
                "aucune_vente": True,
                "lignes_de_la_liste": [],
                "premiere_page": True,
                "a_page_suivante": False,
            }
            return _rendre_vue_ventes(
                request, "laboutik/partial/hx_liste_ventes.html", context
            )

        # Les ventes du service : reglees depuis le debut du service, faites sur un
        # point de vente du lieu (caisse ou tireuse). Une vente en ligne n'a pas de
        # point de vente : elle n'est pas ici. Toutes les natures sont montrees
        # (vente, avoir, correction, carte videe) : ce sont toutes les operations
        # numerotees de ces points de vente.
        # / The service's sales: settled since the service start, made on a point of
        #   sale of the venue. Every nature is shown.
        ventes_du_service = Vente.objects.filter(
            statut=Vente.Statut.REGLEE,
            datetime_encaissement__gte=datetime_ouverture,
            point_de_vente__isnull=False,
        )

        # Les filtres. Un point de vente qui n'est pas un uuid ne garde aucune vente.
        # / Filters. A point of sale that is not a uuid keeps no sale.
        filtre_pv = request.GET.get("pv") or ""
        filtre_moyen = request.GET.get("moyen") or ""

        if filtre_pv:
            try:
                uuid_du_point_de_vente_filtre = uuid_module.UUID(filtre_pv)
                ventes_du_service = ventes_du_service.filter(
                    point_de_vente__uuid=uuid_du_point_de_vente_filtre
                )
            except ValueError:
                ventes_du_service = ventes_du_service.none()

        # Le filtre par moyen garde les ventes qui ont AU MOINS UN REGLEMENT de ce
        # moyen. Le moyen ecrit sur une ligne d'article ne compte pas : une ligne
        # corrigee porte le nouveau moyen, alors que sa vente a ete reglee avec
        # l'ancien (la vente CORRECTION porte le nouveau).
        # / The method filter keeps sales with AT LEAST ONE PAYMENT of that method;
        #   the line's method never counts.
        if filtre_moyen:
            un_reglement_de_ce_moyen = Reglement.objects.filter(
                vente_id=OuterRef("uuid"),
                moyen=filtre_moyen,
            )
            ventes_du_service = ventes_du_service.filter(
                Exists(un_reglement_de_ce_moyen)
            )

        # La suite de la liste : les ventes de numero plus petit que la derniere
        # deja affichee. Un numero illisible donne la premiere page.
        # / The rest of the list: sales numbered below the last one shown.
        numero_de_la_derniere_vente_affichee = None
        try:
            numero_de_la_derniere_vente_affichee = int(request.GET.get("avant", ""))
        except (ValueError, TypeError):
            numero_de_la_derniere_vente_affichee = None
        premiere_page = numero_de_la_derniere_vente_affichee is None
        if not premiere_page:
            ventes_du_service = ventes_du_service.filter(
                numero__lt=numero_de_la_derniere_vente_affichee
            )

        # La plus recente d'abord : le numero suit l'ordre des encaissements.
        # Reglements et point de vente precharges, nombre d'articles annote : le
        # nombre de requetes ne depend pas du nombre de ventes.
        # / Most recent first; prefetched and annotated: constant query count.
        ventes_triees = (
            ventes_du_service.select_related("point_de_vente")
            .prefetch_related("reglements")
            .annotate(quantite_d_articles=Sum("articles__qty"))
            .order_by("-numero")
        )
        ventes_de_la_page = list(ventes_triees[:NOMBRE_DE_VENTES_PAR_PAGE])

        numero_de_la_derniere_vente_de_la_page = None
        a_page_suivante = False
        if ventes_de_la_page:
            numero_de_la_derniere_vente_de_la_page = ventes_de_la_page[-1].numero
            a_page_suivante = ventes_du_service.filter(
                numero__lt=numero_de_la_derniere_vente_de_la_page
            ).exists()
        lignes_de_la_liste = lignes_de_la_liste_des_ventes(ventes_de_la_page)

        # Liste des PV pour le filtre (select)
        # / POS list for the filter (select)
        points_de_vente = (
            PointDeVente.objects.filter(
                hidden=False,
            )
            .order_by("poid_liste")
            .values("uuid", "name")
        )

        context = {
            "aucune_vente": False,
            "lignes_de_la_liste": lignes_de_la_liste,
            "premiere_page": premiere_page,
            "a_page_suivante": a_page_suivante,
            "numero_de_la_derniere_vente_de_la_page": (
                numero_de_la_derniere_vente_de_la_page
            ),
            "filtre_pv": filtre_pv,
            "filtre_moyen": filtre_moyen,
            "points_de_vente": list(points_de_vente),
            # Les moyens du comptoir par leur nom unique (`nom_du_moyen_de_paiement`) ;
            # les moyens cashless et hors argent par un mot de famille, plus court
            # que le libelle de `PaymentMethod`.
            # / Counter methods by their single name; cashless and non-money methods
            #   by a short family word.
            "moyens_paiement": [
                {
                    "code": PaymentMethod.CASH,
                    "label": nom_du_moyen_de_paiement(PaymentMethod.CASH),
                },
                {
                    "code": PaymentMethod.CC,
                    "label": nom_du_moyen_de_paiement(PaymentMethod.CC),
                },
                {
                    "code": PaymentMethod.CHEQUE,
                    "label": nom_du_moyen_de_paiement(PaymentMethod.CHEQUE),
                },
                {"code": PaymentMethod.LOCAL_EURO, "label": _("Cashless")},
                {"code": PaymentMethod.LOCAL_GIFT, "label": _("Cadeau")},
                {
                    "code": PaymentMethod.NON_MONETAIRE,
                    "label": nom_d_une_monnaie_de_points_introuvable(),
                },
            ],
        }
        return _rendre_vue_ventes(
            request, "laboutik/partial/hx_liste_ventes.html", context
        )

    @action(
        detail=False,
        methods=["get"],
        url_path=r"detail-vente/(?P<uuid_vente>[^/.]+)",
        url_name="detail_vente",
    )
    def detail_vente(self, request, uuid_vente=None):
        """
        GET /laboutik/caisse/detail-vente/<uuid de la vente>/
        Detail d'une vente : ses articles, ses reglements, sa vente liee, son statut.
        / Sale detail: its items, payments, linked sale and status.

        LOCALISATION : laboutik/views.py

        FLUX :
        1. La vente, par son uuid (404 si l'adresse n'est pas un uuid ou si la vente
           n'existe pas). Une vente en attente s'affiche aussi, avec son statut.
        2. Le contexte : `_contexte_du_detail_d_une_vente` (articles, reglements,
           boutons « Corriger », ventes liees et derivees).
        3. Rend hx_detail_vente.html.
        / Sale by uuid; context built by `_contexte_du_detail_d_une_vente`.
        """
        contexte_vente_introuvable = {
            "msg_type": "warning",
            "msg_content": _("Vente introuvable"),
            "selector_bt_retour": "#messages",
        }

        # Valider le format UUID avant la requete
        # / Validate UUID format before the query
        try:
            uuid_de_la_vente = uuid_module.UUID(str(uuid_vente))
        except (ValueError, AttributeError):
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                contexte_vente_introuvable,
                status=404,
            )

        vente = (
            Vente.objects.select_related("point_de_vente", "vente_liee")
            .prefetch_related("ventes_derivees", "reglements")
            .filter(uuid=uuid_de_la_vente)
            .first()
        )
        if vente is None:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                contexte_vente_introuvable,
                status=404,
            )

        context = _contexte_du_detail_d_une_vente(vente)
        return _rendre_vue_ventes(
            request, "laboutik/partial/hx_detail_vente.html", context
        )


# --------------------------------------------------------------------------- #
#  Fonctions utilitaires — Menu Ventes                                         #
#  Utility functions — Sales Menu                                              #
# --------------------------------------------------------------------------- #


# Les seuls anciens moyens qu'une correction peut changer : l'argent compte au
# comptoir. Liste POSITIVE : un moyen ajoute un jour a `PaymentMethod` n'est pas
# corrigeable tant qu'il n'est pas ajoute ici.
# / The only old methods a correction may change. A POSITIVE list: a new
#   PaymentMethod is not correctable until it is added here.
MOYENS_CORRIGEABLES_A_LA_CAISSE = (
    PaymentMethod.CASH,
    PaymentMethod.CC,
    PaymentMethod.CHEQUE,
)


def raison_du_refus_de_correction(ligne):
    """
    Dit pourquoi le moyen de paiement de cette ligne ne peut pas etre corrige, ou
    None si la correction est possible.
    / Tells why this line's payment method cannot be corrected, or None.

    LOCALISATION : laboutik/views.py

    Les regles qui ne dependent que de la ligne, dans l'ordre :
    1. Un paiement cashless (NFC) est lie a des transactions fedow_core : le changer
       casserait le registre.
    2. Une vente hors argent (offerte, en points ou en temps) n'a rien encaisse : la
       « corriger » ferait apparaitre de l'argent jamais recu.
    3. Seuls les moyens de `MOYENS_CORRIGEABLES_A_LA_CAISSE` se corrigent (especes,
       CB, cheque).
    4. Seule une vente faite a la caisse (`sale_origin` LABOUTIK) se corrige : une
       vente en ligne a ses propres regles (Stripe, remboursements).
    5. Seule une vente reglee (elle a un numero) se corrige : une ligne sans vente
       n'a pas de vente d'origine, une vente en attente n'a rien encaisse.
    6. Une vente couverte par une cloture journaliere est figee.
    / Line-only rules: not cashless, not non-money, cash/card/cheque only, register
      sale only, settled sale only, not covered by a daily closure.

    FLUX : appelee par `PaiementViewSet.corriger_moyen_paiement` (GARDE 1 : le
    message est renvoye au caissier) et par `CaisseViewSet.detail_vente` (le bouton
    « Corriger moyen » n'est propose que si elle rend None).
    / Called by the correction route (guard 1) and by the sale detail screen.

    :param ligne: la `LigneArticle` cliquee dans l'historique des ventes
    :return: le message de refus (texte traduisible), ou None
    """
    moyen_de_la_ligne = ligne.payment_method

    if moyen_de_la_ligne in MOYENS_CASHLESS:
        return _("Les paiements cashless ne peuvent pas etre modifies")

    if moyen_de_la_ligne in MOYENS_HORS_ARGENT:
        return _(
            "Une vente hors argent (offerte, en points ou en temps) "
            "ne peut pas être corrigée en paiement"
        )

    if moyen_de_la_ligne not in MOYENS_CORRIGEABLES_A_LA_CAISSE:
        return _(
            "Seul un paiement en espèces, par carte bancaire ou par chèque "
            "peut être corrigé."
        )

    if ligne.sale_origin != SaleOrigin.LABOUTIK:
        return _("Seule une vente faite à la caisse peut être corrigée.")

    vente_de_la_ligne = ligne.vente
    la_ligne_a_une_vente_reglee = (
        vente_de_la_ligne is not None and vente_de_la_ligne.numero is not None
    )
    if not la_ligne_a_une_vente_reglee:
        return _("Seule une vente réglée peut être corrigée.")

    if vente_couverte_par_cloture(vente_de_la_ligne):
        return _("Cette vente est couverte par une cloture. Modification interdite.")

    return None


def _calculer_datetime_ouverture_service():
    """
    Calcule le debut du service en cours.
    / Computes the start of the current service.

    LOCALISATION : laboutik/views.py

    Le service couvre TOUTES les origines (caisse, en ligne, tireuse...), comme la J
    qui le cloturera.
    - Le lieu a une cloture journaliere unique (J) : le service commence a la fin
      de la derniere J (la J suivante commencera la aussi). Sans vente reglee depuis
      cette fin, il n'y a pas de service en cours : None.
    - Le lieu n'a aucune J : l'heure de la premiere LIGNE D'ARTICLE des ventes
      reglees du lieu, toutes origines ; None s'il n'y en a pas. Une ligne est
      ecrite quelques millisecondes AVANT l'encaissement de sa vente : partir de la
      ligne (et non de `datetime_encaissement`) garde la premiere vente visible pour
      les ecrans qui lisent encore les lignes par leur heure (`liste_ventes`, rapport
      temps reel).
    Les appelants (ticket X, recapitulatif, sortie de caisse, rapport temps reel,
    liste des ventes) lisent None comme « aucune vente en cours ».
    / Every origin. With a J: the end of the last J, or None without a settled sale
      since. Without any J: the first item line of the settled sales (written just
      before settlement), or None.
    """
    # La cloture est globale au lieu (pas par point de vente).
    # / The closure is global to the venue (not per point of sale).
    derniere_cloture_journaliere = ClotureCaisseUnique.derniere_journaliere()

    if derniere_cloture_journaliere is not None:
        fin_de_la_derniere_j = derniere_cloture_journaliere.datetime_fin
        une_vente_reglee_depuis_la_j = Vente.objects.filter(
            statut=Vente.Statut.REGLEE,
            datetime_encaissement__gte=fin_de_la_derniere_j,
        ).exists()
        if not une_vente_reglee_depuis_la_j:
            return None
        return fin_de_la_derniere_j

    heure_de_la_premiere_ligne_reglee = LigneArticle.objects.filter(
        vente__statut=Vente.Statut.REGLEE,
    ).aggregate(premiere_heure=Min("datetime"))["premiere_heure"]
    return heure_de_la_premiere_ligne_reglee


# --------------------------------------------------------------------------- #
#  Une vente a l'ecran : liste et detail des ventes de la caisse               #
#  A sale on screen: register sales list and detail                            #
# --------------------------------------------------------------------------- #

# Le nombre de ventes d'une page de la liste (la suite arrive au defilement).
# / Number of sales per list page (the rest arrives on scroll).
NOMBRE_DE_VENTES_PAR_PAGE = 20


def lignes_que_la_correction_deplace(ligne):
    """
    Les lignes dont une correction de moyen change le moyen : les lignes de la MEME
    VENTE qui portent le meme moyen ACTUEL que la ligne cliquee. Une ligne sans vente
    (ecrite avant les ventes) est seule.
    / The lines a payment method correction moves: the lines of the SAME SALE with
    the same CURRENT method as the clicked line.

    LOCALISATION : laboutik/views.py

    C'est la seule definition de « ce que la correction deplace » : l'ecran du
    formulaire affiche la somme de leurs `total_ttc`, et la route
    `corriger_moyen_paiement` deplace exactement cette somme. Elle lit le moyen
    ACTUEL des lignes : apres une correction especes → CB, les lignes portent CB, et
    une deuxieme correction (CB → cheque) deplace ces memes lignes.
    / The single definition, read by the form screen and by the route. It reads the
    CURRENT method, so a second correction moves the same lines again.

    Les deux appelants refusent d'abord une ligne sans vente reglee
    (`raison_du_refus_de_correction`) : la ligne a toujours une vente ici.
    / Both callers first refuse a line without a settled sale.

    :param ligne: la `LigneArticle` cliquee (avec sa vente)
    :return: liste de `LigneArticle` (au moins la ligne elle-meme)
    """
    lignes_du_meme_moyen = list(
        LigneArticle.objects.filter(
            vente_id=ligne.vente_id,
            payment_method=ligne.payment_method,
        ).order_by("datetime", "pk")
    )
    return lignes_du_meme_moyen


def vente_imprimable_a_la_caisse(vente):
    """
    Dit si le ticket de cette vente s'imprime a la caisse : une vente ou un avoir,
    reglee, faite sur un point de vente du lieu. Une correction ou un vidage de
    carte n'ont pas de ticket client ; une vente en ligne non plus (ni point de
    vente, ni imprimante a elle).
    / Whether this sale's receipt prints at the register: a settled sale or credit
    note made on a point of sale.

    LOCALISATION : laboutik/views.py

    APPELE PAR : `_contexte_du_detail_d_une_vente` (bouton « Ré-imprimer ») et
    `PaiementViewSet.imprimer_ticket` (refus) : la meme regle.

    :param vente: la `Vente`
    :return: bool
    """
    nature_avec_ticket = vente.nature in (Vente.Nature.VENTE, Vente.Nature.AVOIR)
    return (
        vente.statut == Vente.Statut.REGLEE
        and nature_avec_ticket
        and vente.point_de_vente_id is not None
    )


def _uuid_de_la_vente_du_paiement(uuid_transaction):
    """
    L'uuid (texte) de la vente reglee d'un paiement de caisse, pour le bouton
    « Imprimer » de l'ecran de fin de paiement ; "" si elle n'existe pas (rien a
    imprimer).
    / The settled sale's uuid of a register payment, for the success screen's print
    button; "" if none.

    LOCALISATION : laboutik/views.py

    La caisse ouvre la vente d'un paiement avec l'identifiant du paiement comme
    cle d'idempotence (`ouvrir_vente(..., idempotency_key=str(uuid_transaction))`,
    tous les chemins de paiement de la caisse). On la retrouve par cette cle : les
    ecrans de fin de paiement sont rendus par huit chemins, qui ne gardent pas tous
    la vente sous la main.
    / The register opens a payment's sale with the payment id as idempotency key:
    the sale is found by that key.

    :param uuid_transaction: l'identifiant du paiement (uuid ou texte)
    :return: texte
    """
    vente_du_paiement = (
        Vente.objects.filter(
            idempotency_key=str(uuid_transaction),
            statut=Vente.Statut.REGLEE,
        )
        .only("uuid")
        .first()
    )
    if vente_du_paiement is None:
        return ""
    return str(vente_du_paiement.uuid)


def _refus_de_correction(request, message, ligne_uuid, status=400):
    """
    La reponse d'un refus de correction : le message, rendu dans la zone du
    formulaire de cette ligne (`#correction-zone-<uuid>`). Le formulaire vise le
    detail entier (re-rendu apres une correction reussie) : sans `HX-Retarget`, un
    refus effacerait le detail.
    / A correction refusal, rendered in the line's form zone (HX-Retarget), so a
    refusal does not replace the whole detail.

    LOCALISATION : laboutik/views.py

    :param message: le texte du refus (traduit)
    :param ligne_uuid: l'uuid de la ligne du formulaire
    :param status: le code HTTP (400 par defaut, 404 pour une ligne introuvable)
    :return: HttpResponse
    """
    reponse = render(
        request,
        "laboutik/partial/hx_messages.html",
        {"msg_type": "warning", "msg_content": message},
        status=status,
    )
    reponse["HX-Retarget"] = f"#correction-zone-{ligne_uuid}"
    reponse["HX-Reswap"] = "innerHTML"
    return reponse


def _contexte_du_detail_d_une_vente(vente):
    """
    Le contexte de l'ecran du detail d'une vente (`hx_detail_vente.html`).
    / The context of a sale's detail screen.

    LOCALISATION : laboutik/views.py

    FLUX :
    1. Les articles : `articles_de_la_vente_pour_l_affichage` (un article paye avec
       deux moyens reste UN article, quantite reelle).
    2. Les reglements : `reglements_pour_l_affichage` (moyen, monnaie, montant).
    3. Un bouton « Corriger » par moyen ACTUEL des lignes qui se corrige (especes,
       CB, cheque) : il ouvre la correction d'une ligne de ce moyen, si
       `raison_du_refus_de_correction` l'accepte (seule source du refus, partagee
       avec la route). Une vente deja corrigee garde donc un bouton pour son
       nouveau moyen : on peut corriger une correction erronee.
    4. La vente liee (origine d'un avoir ou d'une correction) et les ventes qui en
       derivent (« Corrigée par la vente n° X »), avec leur lien.
    APPELE PAR : `CaisseViewSet.detail_vente` et `PaiementViewSet.corriger_moyen_paiement`
    (le detail est re-rendu apres une correction).
    / Items, payments, one Correct button per current correctable method, linked and
    derived sales. Called by the detail screen and after a correction.

    :param vente: la `Vente` (lue avec `point_de_vente`, `vente_liee` et
        `ventes_derivees`)
    :return: dict de contexte
    """
    lignes_de_la_vente = list(
        LigneArticle.objects.filter(vente=vente)
        .select_related(
            "pricesold__productsold__product__stock_inventaire",
            "pricesold__productsold__event",
            "pricesold__price",
        )
        .order_by("datetime", "pk")
    )
    reglements_de_la_vente = list(vente.reglements.all())

    # L'unite des montants, puis les articles et les reglements a afficher.
    # / The amount unit, then the items and payments to display.
    nom_par_uuid_de_monnaie = noms_des_monnaies_des_ventes([vente])
    nom_de_l_unite = nom_de_l_unite_de_la_vente(vente, nom_par_uuid_de_monnaie)
    articles_affiches = articles_de_la_vente_pour_l_affichage(
        lignes_de_la_vente, nom_de_l_unite
    )
    reglements_affiches = reglements_pour_l_affichage(
        reglements_de_la_vente, nom_par_uuid_de_monnaie, nom_de_l_unite
    )

    # Le total de la vente : la somme des nets vendus de ses articles (une vente en
    # attente n'a pas encore ses totaux stockes).
    # / The sale total: the sum of its items' net totals.
    total_de_la_vente = 0
    for article_affiche in articles_affiches:
        total_de_la_vente += article_affiche["total"]

    # Un bouton « Corriger » par moyen actuel des lignes qui se corrige.
    # / One "Correct" button per current correctable line method.
    boutons_de_correction = []
    moyens_deja_proposes = set()
    for ligne in lignes_de_la_vente:
        moyen_de_la_ligne = ligne.payment_method
        moyen_corrigeable = moyen_de_la_ligne in MOYENS_CORRIGEABLES_A_LA_CAISSE
        if not moyen_corrigeable or moyen_de_la_ligne in moyens_deja_proposes:
            continue
        moyens_deja_proposes.add(moyen_de_la_ligne)
        if raison_du_refus_de_correction(ligne) is not None:
            continue
        boutons_de_correction.append(
            {
                "ligne_uuid": str(ligne.uuid),
                "libelle_du_moyen": nom_du_moyen_de_paiement(moyen_de_la_ligne),
            }
        )

    # La vente d'origine d'un avoir ou d'une correction, et les ventes qui derivent
    # de celle-ci (prechargees). Une vente derivee pas encore reglee n'a pas de
    # numero : elle n'est pas montree.
    # / The original sale, and the settled sales derived from this one.
    vente_liee = None
    if vente.vente_liee is not None:
        vente_liee = {
            "uuid": vente.vente_liee.uuid,
            "numero": vente.vente_liee.numero,
            "badge_de_la_nature": badge_de_la_nature_d_une_vente(
                vente.vente_liee.nature
            ),
        }
    ventes_derivees = []
    ventes_derivees_prechargees = vente.ventes_derivees.all()
    for vente_derivee in ventes_derivees_prechargees:
        if vente_derivee.numero is None:
            continue
        ventes_derivees.append(
            {
                "uuid": vente_derivee.uuid,
                "nature": vente_derivee.nature,
                "badge_de_la_nature": badge_de_la_nature_d_une_vente(
                    vente_derivee.nature
                ),
                "phrase": phrase_d_une_vente_derivee(vente_derivee),
            }
        )

    heure_de_la_vente = vente.datetime_encaissement or vente.datetime_creation
    heure_locale_de_la_vente = heure_de_la_vente.astimezone(
        Configuration.get_solo().get_tzinfo()
    )

    nom_pv = ""
    if vente.point_de_vente is not None:
        nom_pv = vente.point_de_vente.name

    return {
        "vente": vente,
        "vente_imprimable": vente_imprimable_a_la_caisse(vente),
        "statut_de_la_vente": vente.get_statut_display(),
        "badge_de_la_nature": badge_de_la_nature_d_une_vente(vente.nature),
        "date_et_heure": heure_locale_de_la_vente.strftime("%d/%m/%Y %H:%M"),
        "nom_pv": nom_pv,
        "articles": articles_affiches,
        "reglements": reglements_affiches,
        "total_a_la_francaise": montant_a_la_francaise_dans_l_unite(
            total_de_la_vente, nom_de_l_unite
        ),
        "boutons_de_correction": boutons_de_correction,
        "vente_liee": vente_liee,
        "ventes_derivees": ventes_derivees,
    }


def _contexte_de_l_ecran_du_z(cloture):
    """
    Le contexte de l'ecran du Z (`hx_cloture_rapport.html`) : l'essentiel du rapport
    stocke dans la J, mis en forme par `comptabilite/presentation.py`.
    / The Z screen context: the essential sections of the J's stored report.

    LOCALISATION : laboutik/views.py

    L'ecran montre le chiffre d'affaires, les reglements (argent, cashless, hors
    argent : offerts et points), le tiroir (caisse especes) et la phrase de
    reconciliation, plus un lien vers la fiche complete de la cloture dans l'admin.
    Aucune regle d'affichage n'est recopiee ici : les sections viennent telles
    quelles de `sections_pour_affichage`.
    / Revenue, payments, cash drawer, reconciliation sentence, and a link to the
      admin page. No display rule is copied here.

    :param cloture: la `comptabilite.ClotureCaisse` (J) creee par le bouton
    :return: dict de contexte
    """
    sections_par_cle = {}
    sections_du_rapport = sections_pour_affichage(cloture.rapport_json)
    for section in sections_du_rapport:
        sections_par_cle[section["cle"]] = section

    phrase_de_reconciliation = ""
    section_de_reconciliation = sections_par_cle.get("reconciliation")
    if section_de_reconciliation is not None:
        phrase_de_reconciliation = section_de_reconciliation["phrase"]

    return {
        "cloture": cloture,
        "chiffre_affaires_ttc_a_la_francaise": euros_a_la_francaise(
            cloture.total_general
        ),
        "section_chiffre_affaires": sections_par_cle.get("chiffre_affaires"),
        "section_reglements": sections_par_cle.get("reglements"),
        "section_caisse_especes": sections_par_cle.get("caisse_especes"),
        "phrase_de_reconciliation": phrase_de_reconciliation,
        "adresse_de_la_fiche_de_la_cloture": reverse(
            "staff_admin:comptabilite_cloturecaisse_change", args=[cloture.pk]
        ),
    }


def _contexte_du_recap_du_service(rapport_du_service):
    """
    Le contexte de l'ecran complet du recapitulatif en cours
    (`hx_recap_en_cours.html`) : les chiffres du haut et toutes les sections du
    rapport X, mises en forme par `comptabilite/presentation.py` (aucune regle
    d'affichage recopiee ici).
    / The current recap screen context: top figures and every X report section,
      formatted by the shared presentation.

    LOCALISATION : laboutik/views.py

    :param rapport_du_service: dict de `RapportDesVentes(debut, maintenant).rapport_x()`
    :return: dict de contexte
    """
    tiroir = rapport_du_service["caisse_especes"]
    return {
        "chiffre_affaires_ttc_a_la_francaise": euros_a_la_francaise(
            rapport_du_service["chiffre_affaires"]["total_ttc_en_centimes"]
        ),
        "nombre_d_operations": rapport_du_service["en_tete"]["nombre_de_ventes"],
        "fond_de_caisse_a_la_francaise": euros_a_la_francaise(
            tiroir["fond_de_caisse_en_centimes"]
        ),
        "solde_du_tiroir_a_la_francaise": euros_a_la_francaise(
            tiroir["solde_theorique_en_centimes"]
        ),
        "sections_du_rapport": sections_pour_affichage(rapport_du_service),
    }


def _section_du_tiroir_du_service_en_cours():
    """
    La section « caisse especes » du tiroir en cours, toujours calculee par le
    rapport des ventes (`RapportDesVentes.section_caisse_especes`), jusqu'a
    maintenant.
    / The current cash drawer section, always computed by the sales report.

    LOCALISATION : laboutik/views.py

    LE DEBUT DU TIROIR :
    - le lieu a une J : la fin de la derniere J, MEME SANS VENTE depuis. Une sortie
      de caisse faite apres la J et avant la premiere vente compte donc tout de
      suite dans le solde (la J suivante la comptera aussi) ;
    - le lieu n'a aucune J : le debut du service (`_calculer_datetime_ouverture_service`) ;
      sans vente reglee non plus, maintenant : le tiroir ne contient que le fond.
    / With a J: the end of the last J, even without a sale since (a withdrawal made
      before the first sale counts at once). Without a J: the service start, or now.

    :return: dict de la section (montants en centimes, signes comme dans le rapport)
    """
    maintenant = dj_timezone.now()
    derniere_cloture_journaliere = ClotureCaisseUnique.derniere_journaliere()
    if derniere_cloture_journaliere is not None:
        debut_du_tiroir = derniere_cloture_journaliere.datetime_fin
    else:
        debut_du_tiroir = _calculer_datetime_ouverture_service()
        if debut_du_tiroir is None:
            debut_du_tiroir = maintenant
    return RapportDesVentes(debut_du_tiroir, maintenant).section_caisse_especes()


def _lignes_du_tiroir_pour_l_ecran(section_du_tiroir):
    """
    Les lignes du tiroir pour l'ecran de sortie de caisse, ecrites par la
    presentation partagee (`comptabilite/presentation.py` `lignes_du_tiroir`) :
    fond, especes recues, especes rendues, corrections, sorties, solde theorique,
    montants signes (l'argent qui sort est negatif), comme le ticket X.
    / The drawer lines for the cash withdrawal screen, written by the shared
      presentation, signed like the X ticket.

    LOCALISATION : laboutik/views.py

    :param section_du_tiroir: dict de la section « caisse especes »
    :return: liste de {"libelle", "montant"} (textes)
    """
    lignes_signees_du_tiroir = lignes_du_tiroir(section_du_tiroir)
    lignes_pour_l_ecran = []
    for ligne_du_tiroir in lignes_signees_du_tiroir:
        lignes_pour_l_ecran.append(
            {
                "libelle": ligne_du_tiroir["libelle"],
                "montant": euros_a_la_francaise(ligne_du_tiroir["montant_en_centimes"]),
            }
        )
    return lignes_pour_l_ecran


def _construire_params_ventes(uuid_pv, tag_id_cm, type_app):
    """
    Construit la query string a propager dans toutes les URLs des vues Ventes.
    / Builds the query string propagated in every Sales view URL.

    LOCALISATION : laboutik/views.py

    Les onglets Ventes font un hx-push-url avec "?vue=...&{{ params_ventes }}".
    Si un parametre manque ici, il disparait de l'URL du navigateur.
    C'est pour ca qu'on garde les 3 parametres : uuid_pv, tag_id_cm et type_app.
    Sans uuid_pv, on renvoie une chaine vide (pas de point de vente a propager).
    / Sales tabs push "?vue=...&{{ params_ventes }}" to the URL.
    A missing param here disappears from the browser URL.

    :param uuid_pv: UUID du point de vente courant (str, peut etre vide)
    :param tag_id_cm: tag de la carte primaire (str, peut etre vide)
    :param type_app: type d'application cliente (str, peut etre vide)
    :return: "uuid_pv=...&tag_id_cm=...&type_app=..." ou ""
    """
    if not uuid_pv:
        return ""

    parametres_a_propager = {
        "uuid_pv": uuid_pv,
        "tag_id_cm": tag_id_cm,
        "type_app": type_app,
    }
    return urlencode(parametres_a_propager)


def _construire_contexte_ventes(request):
    """
    Construit le contexte commun des vues Ventes (header + params retour).
    Les params uuid_pv et tag_id_cm sont propages dans les URLs HTMX
    pour que le bouton Retour et les onglets fonctionnent.
    / Builds common context for Sales views (header + return params).
    uuid_pv and tag_id_cm params are propagated in HTMX URLs
    so that the Back button and tabs work.

    LOCALISATION : laboutik/views.py
    """
    uuid_pv = request.GET.get("uuid_pv", "")
    tag_id_cm = request.GET.get("tag_id_cm", "")

    # Charger le PV et la carte primaire pour le header
    # / Load POS and primary card for the header
    pv_dict = {"id": uuid_pv, "name": "", "icon": "", "comportement": "D"}
    card_dict = {"tag_id": tag_id_cm, "name": "", "mode_gerant": False, "pvs_list": []}

    if uuid_pv:
        try:
            pv_obj = PointDeVente.objects.get(uuid=uuid_pv)
            pv_dict["name"] = pv_obj.name
            pv_dict["icon"] = pv_obj.icon or ""
            pv_dict["comportement"] = pv_obj.comportement
        except (PointDeVente.DoesNotExist, ValueError):
            pass

    if tag_id_cm:
        carte_primaire_obj, _erreur = _charger_carte_primaire(tag_id_cm)
        if carte_primaire_obj is not None:
            card_dict["name"] = str(
                carte_primaire_obj.carte.number or carte_primaire_obj.carte.tag_id
            )
            card_dict["mode_gerant"] = carte_primaire_obj.edit_mode
            pvs_list = list(
                carte_primaire_obj.points_de_vente.filter(hidden=False)
                .order_by("poid_liste")
                .values_list("uuid", "name", "poid_liste", "icon")
            )
            card_dict["pvs_list"] = [
                {
                    "uuid": str(uuid),
                    "name": name,
                    "poid_liste": poid,
                    "icon": icon or "",
                }
                for uuid, name, poid, icon in pvs_list
            ]

    # Params a propager dans toutes les URLs HTMX des vues Ventes
    # / Params to propagate in all HTMX URLs of Sales views
    type_app = request.GET.get("type_app", "")
    params_ventes = _construire_params_ventes(uuid_pv, tag_id_cm, type_app)

    # URL de retour vers l'interface POS
    # / Return URL to the POS interface
    url_retour_pv = reverse("laboutik-caisse-point_de_vente")
    if params_ventes:
        url_retour_pv += f"?{params_ventes}"

    laboutik_config = LaboutikConfiguration.get_solo()

    # state et stateJson : necessaires pour base.html (JS init)
    # Un state minimal suffit pour les vues Ventes (pas de NFC, pas de panier)
    # / state and stateJson: needed for base.html (JS init)
    # A minimal state is enough for Sales views (no NFC, no cart)
    state = _construire_state(user=request.user)

    return {
        "pv": pv_dict,
        "card": card_dict,
        "title": _("Ventes"),
        "hide_pv_name": True,
        "url_retour_pv": url_retour_pv,
        "params_ventes": params_ventes,
        "mode_ecole": laboutik_config.mode_ecole,
        "state": state,
        "stateJson": dumps(state),
    }


def _rendre_vue_ventes(request, template_partiel, context):
    """
    Rend une vue Ventes : page complete (body swap) ou partial (zone swap).
    Si la requete HTMX cible #ventes-zone, on rend juste le partial.
    Sinon (navigation depuis le burger menu), on rend la page complete
    avec le header et le wrapper ventes.html.
    / Renders a Sales view: full page (body swap) or partial (zone swap).
    If the HTMX request targets #ventes-zone, render just the partial.
    Otherwise (nav from burger menu), render full page with header.

    LOCALISATION : laboutik/views.py
    """
    # Ajouter le contexte header/retour commun
    # / Add common header/return context
    context_ventes = _construire_contexte_ventes(request)
    context.update(context_ventes)

    # Page complete seulement si :
    # - Pas de requete HTMX (acces direct via URL)
    # - OU target == "body" (navigation depuis burger menu)
    # Tout le reste (onglets, scroll infini, filtres) = partial seul.
    # / Full page only if:
    # - Not an HTMX request (direct URL access)
    # - OR target == "body" (navigation from burger menu)
    # Everything else (tabs, infinite scroll, filters) = partial only.
    # Le <body> a id="contenu" dans base.html — htmx envoie "contenu" pas "body".
    # On accepte les deux + l'acces direct sans HTMX.
    # / <body> has id="contenu" in base.html — htmx sends "contenu" not "body".
    # We accept both + direct URL access without HTMX.
    est_navigation_complete = (
        not hasattr(request, "htmx")
        or not request.htmx
        or request.htmx.target in ("body", "contenu")
    )

    if not est_navigation_complete:
        # Swap interne : juste le partial (onglets, pagination, detail)
        # / Internal swap: just the partial (tabs, pagination, detail)
        return render(request, template_partiel, context)
    else:
        # Navigation complete : page avec header + wrapper
        # / Full navigation: page with header + wrapper
        context["vue_partiel"] = template_partiel
        type_app = request.GET.get("type_app", "unknown")
        context["type_app"] = type_app
        return render(request, "laboutik/views/ventes.html", context)


# --------------------------------------------------------------------------- #
#  Fonctions utilitaires — paiement ORM (Phase 2)                             #
#  Utility functions — ORM payment (Phase 2)                                  #
# --------------------------------------------------------------------------- #

# Correspondance entre les codes de moyens de paiement de l'interface
# et les valeurs de l'enum PaymentMethod dans BaseBillet.
# Mapping between interface payment method codes and BaseBillet PaymentMethod enum.
MAPPING_CODES_PAIEMENT = {
    "carte_bancaire": PaymentMethod.CC,
    "CH": PaymentMethod.CHEQUE,
    "espece": PaymentMethod.CASH,
    "gift": PaymentMethod.FREE,
    "nfc": PaymentMethod.LOCAL_EURO,  # TLF = token local fiduciaire adossé à l'euro
}

# Ordre de priorité pour la cascade de débit NFC fiduciaire.
# Cadeau d'abord (offert au lieu), puis local (déjà encaissé à la recharge),
# puis fédéré (frais Stripe pour le lieu).
# Ordre fixe, pas configurable par tenant (décision brainstorming 2026-04-08).
# / Priority order for NFC fiduciary debit cascade.
# Gift first (free to venue), then local (already cashed at top-up),
# then federated (Stripe fees for venue).
# Fixed order, not configurable per tenant.
ORDRE_CASCADE_FIDUCIAIRE = [Asset.TNF, Asset.TLF, Asset.FED]

# Mapping catégorie d'Asset → PaymentMethod pour les LigneArticle.
# Permet aux rapports de distinguer les paiements cadeau (LG) des paiements
# monnaie locale (LE) dans le Ticket X et la clôture.
# On le lit par accès direct [categorie], jamais avec un repli : une catégorie
# absente du mapping ne doit pas être enregistrée en euros.
# / Asset category → PaymentMethod mapping for LigneArticle. Read with direct
#   access, never with a fallback: an unknown category must not become euros.
MAPPING_ASSET_CATEGORY_PAYMENT_METHOD = {
    Asset.TNF: PaymentMethod.LOCAL_GIFT,  # LG — cadeau
    Asset.TLF: PaymentMethod.LOCAL_EURO,  # LE — monnaie locale
    Asset.FED: PaymentMethod.STRIPE_FED,  # SF — monnaie fédérée du réseau (PAS de la monnaie locale)
    Asset.TIM: PaymentMethod.NON_MONETAIRE,  # NM — temps, pas de l'argent
    Asset.FID: PaymentMethod.NON_MONETAIRE,  # NM — fidélité, pas de l'argent
}

# Constante Decimal pour arrondir les qty partielles à 6 décimales.
# / Decimal constant for rounding partial qty to 6 decimal places.
SIX_DECIMALES = Decimal("0.000001")


def _calculer_qty_partielles(lignes_avec_amounts, prix_unitaire_centimes, qty_totale):
    """
    Calcule les qty partielles pour N lignes d'un même article splitté.
    / Computes partial qty for N lines of the same split article.

    LOCALISATION : laboutik/views.py

    Chaque ligne a un amount_centimes (entier). La qty est proportionnelle
    au montant. La dernière ligne prend le reste pour que la somme soit exacte.
    / Each line has an amount_centimes (integer). Qty is proportional
    to the amount. Last line takes the remainder so the sum is exact.

    Exemple / Example:
        Article 3€ (300 centimes), qty=1, splitté en 3 :
        - Ligne 1 : 100 centimes → qty = 0.333333
        - Ligne 2 : 100 centimes → qty = 0.333333
        - Ligne 3 : 100 centimes → qty = 0.333334 (reste)
        Somme qty = 1.000000 exactement.

    :param lignes_avec_amounts: list de dicts avec clé "amount_centimes"
    :param prix_unitaire_centimes: int (prix unitaire en centimes pour qty=1)
    :param qty_totale: Decimal (quantité totale de l'article)
    :return: list de dicts enrichis avec clé "qty" ajoutée
    """
    nombre_de_lignes = len(lignes_avec_amounts)

    # Cas trivial : 1 seule ligne = qty complète
    # / Trivial case: 1 line = full qty
    if nombre_de_lignes == 1:
        lignes_avec_amounts[0]["qty"] = qty_totale
        return lignes_avec_amounts

    # Cas article gratuit : prix=0 → toute la qty sur la 1ère ligne, 0 sur les autres
    # / Free article case: price=0 → all qty on first line, 0 on others
    if prix_unitaire_centimes == 0:
        for i, ligne in enumerate(lignes_avec_amounts):
            ligne["qty"] = qty_totale if i == 0 else Decimal("0")
        return lignes_avec_amounts

    # Cas général : N lignes, calcul proportionnel
    # / General case: N lines, proportional calculation
    somme_qty_precedentes = Decimal("0")

    for i, ligne in enumerate(lignes_avec_amounts):
        est_derniere_ligne = i == nombre_de_lignes - 1

        if est_derniere_ligne:
            # Dernière ligne : prend le reste exact
            # / Last line: takes the exact remainder
            ligne["qty"] = qty_totale - somme_qty_precedentes
        else:
            # Lignes intermédiaires : qty = montant_ligne / prix_unitaire.
            # NE PAS multiplier par qty_totale : amount_centimes est DÉJÀ le montant
            # monétaire de la part (pas une fraction), et le prix unitaire seul donne
            # le nombre d'articles que cette part représente. Multiplier par qty_totale
            # gonflait la qty d'un facteur qty_totale (ex: 3 vins, part 6 € → 3,6 au lieu
            # de 1,2), rendant la dernière ligne NÉGATIVE.
            # / qty = part_amount / unit_price. Do NOT multiply by qty_totale: the part
            # amount already is the monetary share; the unit price alone yields the
            # number of articles it represents. Multiplying by qty_totale inflated qty
            # (e.g. 3 wines, 6 € part → 3.6 instead of 1.2), making the last line NEGATIVE.
            qty_proportionnelle = (
                Decimal(ligne["amount_centimes"])
                / Decimal(prix_unitaire_centimes)
            ).quantize(SIX_DECIMALES)
            ligne["qty"] = qty_proportionnelle
            somme_qty_precedentes += qty_proportionnelle

    return lignes_avec_amounts


def _lire_cle_idempotence_paiement(donnees_post):
    """
    Lit la cle d'idempotence du paiement envoyee par le formulaire.
    / Reads the payment idempotency key sent by the form.

    LOCALISATION : laboutik/views.py

    La cle est creee par le serveur dans moyens_paiement() et posee dans
    #addition-form (champ cle_idempotence_paiement), ou directement dans
    #card-recharge-form (hx_card_recharge.html).
    / The key is created by moyens_paiement() or put in #card-recharge-form.

    :param donnees_post: QueryDict du POST
    :return: uuid.UUID, ou None si absente ou mal formee (ancien client)
    """
    valeur_recue = donnees_post.get("cle_idempotence_paiement", "")
    if not valeur_recue:
        return None
    try:
        return uuid_module.UUID(str(valeur_recue))
    except ValueError:
        return None


def _numero_de_verrou_du_paiement(cle_idempotence):
    """
    Texte qui identifie le verrou PostgreSQL de ce paiement.
    On ajoute le schema du lieu : deux lieux n'attendent jamais l'un l'autre.
    / Text naming the PostgreSQL lock of this payment, prefixed by the tenant schema.
    """
    return f"laboutik-paiement:{connection.schema_name}:{cle_idempotence}"


def _executer_avec_cle_idempotence(request, fonction_de_paiement):
    """
    Execute un paiement une seule fois par cle d'idempotence.
    / Runs a payment only once per idempotency key.

    LOCALISATION : laboutik/views.py

    Appelee par payer() et payer_complementaire().

    LE PROBLEME : un double appui sur « Valider » (ou un renvoi apres une
    coupure reseau) envoie deux fois le meme paiement. Sans protection,
    le client est debite deux fois.
    / A double tap (or a network retry) sends the same payment twice.

    LA SOLUTION :
    1. On pose un verrou PostgreSQL sur la cle (pg_advisory_lock).
       La 2e requete attend que la 1re ait fini.
    2. On regarde si une LigneArticle porte deja cette cle (uuid_transaction).
       Si oui : le paiement est deja fait, on ne rejoue rien.
    3. Sinon, on execute le paiement. La cle devient son uuid_transaction.
    4. On retire le verrou, meme en cas d'erreur (finally).
    / 1. PostgreSQL lock on the key. 2. A LigneArticle already carries it →
    already paid, replay nothing. 3. Otherwise pay, the key becomes the
    uuid_transaction. 4. Always release the lock.

    Pourquoi un verrou de SESSION et pas un bloc atomic() autour de tout :
    les fonctions de paiement ont deja leurs propres blocs atomic. Les
    englober changerait ce qui est annule en cas d'erreur. Le verrou de
    session ne touche pas aux transactions. ATOMIC_REQUESTS est desactive :
    la 1re requete a donc tout valide en base avant de rendre le verrou.
    / Session lock, not an outer atomic(): payment code already has its own
    atomic blocks. ATOMIC_REQUESTS is off, so the first request has committed
    before releasing the lock.

    Pourquoi pas cache.add() : si memcached tombe, tous les paiements seraient
    refuses (voir ignore_exc dans settings.py).
    / Not cache.add(): a memcached outage would block every payment.

    :param request: requete Django (POST)
    :param fonction_de_paiement: methode a appeler, avec la signature
        (request, uuid_transaction_impose=None)
    :return: la reponse HTML du paiement, ou un message « deja enregistre »
    """
    cle_idempotence = _lire_cle_idempotence_paiement(request.POST)

    # Pas de cle : ancien client, ou parcours qui ne passe pas par
    # moyens_paiement. On paie comme avant.
    # / No key: old client or path skipping moyens_paiement. Pay as before.
    if cle_idempotence is None:
        return fonction_de_paiement(request)

    numero_de_verrou = _numero_de_verrou_du_paiement(cle_idempotence)
    with connection.cursor() as curseur:
        curseur.execute("SELECT pg_advisory_lock(hashtext(%s))", [numero_de_verrou])
    try:
        # Deux traces possibles d'un paiement déjà fait : ses lignes (tous les chemins)
        # ou sa vente (chemins passés au service de vente : `Vente.idempotency_key`
        # reprend la clé). L'une OU l'autre suffit à ne rien rejouer.
        # / Two traces of a payment already made: its lines or its sale. Either one
        #   is enough to replay nothing.
        lignes_deja_enregistrees = LigneArticle.objects.filter(
            uuid_transaction=cle_idempotence
        ).exists()
        vente_deja_enregistree = Vente.objects.filter(
            idempotency_key=str(cle_idempotence)
        ).exists()
        paiement_deja_enregistre = lignes_deja_enregistrees or vente_deja_enregistree
        if paiement_deja_enregistre:
            logger.warning(
                f"Paiement en double ignore (cle {cle_idempotence}) : "
                f"les lignes existent deja"
            )
            contexte_deja_enregistre = {
                "action": "initUrlAddition();",
                "msg_type": "success",
                "msg_content": _(
                    "Ce paiement est déjà enregistré. Il n'a pas été encaissé une deuxième fois."
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", contexte_deja_enregistre
            )

        return fonction_de_paiement(request, uuid_transaction_impose=cle_idempotence)
    finally:
        with connection.cursor() as curseur:
            curseur.execute(
                "SELECT pg_advisory_unlock(hashtext(%s))", [numero_de_verrou]
            )


def _diviseur_de_la_quantite_saisie(produit):
    """
    Le nombre qui convertit la quantité saisie au poids ou au volume dans l'unité du
    prix : 1000 (grammes → kilo) ou 100 (centilitres → litre).
    / Converts the typed weight/volume into the price unit: 1000 (g → kg) or 100 (cl → L).

    LOCALISATION : laboutik/views.py

    Une seule règle pour le prix (`_montant_poids_mesure_en_centimes`) et pour le coût
    d'achat (`_creer_lignes_articles`) : les deux doivent diviser de la même façon.
    / One rule for the price and the purchase cost: both must divide the same way.

    :param produit: Product vendu au poids/mesure
    :return: Decimal (1000 ou 100)
    """
    # getattr avec defaut marche sur une relation OneToOne inverse absente
    # (RelatedObjectDoesNotExist herite d'AttributeError).
    # Sans stock, on suppose des grammes, comme la tuile.
    # / getattr default works on a missing reverse OneToOne. No stock → grams.
    stock_du_produit = getattr(produit, "stock_inventaire", None)
    unite_en_centilitres = stock_du_produit is not None and stock_du_produit.unite == "CL"
    if unite_en_centilitres:
        return Decimal(100)
    return Decimal(1000)


def _montant_poids_mesure_en_centimes(produit, prix_obj, quantite_saisie):
    """
    Calcule le prix d'une vente au poids ou au volume, en centimes.
    / Computes the price of a weight/volume sale, in cents.

    LOCALISATION : laboutik/views.py

    Le tarif porte un prix de reference : prix au kg (stock en grammes)
    ou prix au litre (stock en centilitres). Le caissier saisit une quantite
    en g ou en cl. On divise donc par 1000 (g → kg) ou par 100 (cl → L).
    C'est la meme regle que la tuile (_construire_donnees_articles, unite_saisie_label)
    et que l'affichage dans tarif.js (data-diviseur).
    / The price is per kg (stock in grams) or per litre (stock in cl).
    Same rule as the tile and tarif.js: divide by 1000 (g) or 100 (cl).

    Exemple : 350 g de comte a 20 €/kg → 350 / 1000 x 2000 = 700 centimes.

    :param produit: Product vendu au poids/mesure
    :param prix_obj: Price avec poids_mesure=True (prix de reference en euros)
    :param quantite_saisie: int, quantite en g ou en cl (> 0)
    :return: int, montant en centimes (arrondi au centime le plus proche)
    """
    diviseur = _diviseur_de_la_quantite_saisie(produit)

    prix_de_reference_en_centimes = Decimal(prix_obj.prix) * 100
    montant_en_centimes = (
        Decimal(quantite_saisie) / diviseur * prix_de_reference_en_centimes
    )
    return int(montant_en_centimes.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _extraire_articles_du_panier(donnees_post, point_de_vente):
    """
    Extrait les articles du formulaire POST et les charge depuis la DB.
    Extracts articles from the POST form and loads them from DB.

    LOCALISATION : laboutik/views.py

    Le formulaire d'addition envoie les quantités avec les clés :
    - "repid-<product_uuid>" (articles mono-tarif, ancien format)
    - "repid-<product_uuid>--<price_uuid>" (articles multi-tarif)
    - "custom-<product_uuid>--<price_uuid>" (montant prix libre en centimes)
    The addition form sends quantities with keys:
    - "repid-<product_uuid>" (single-rate articles, old format)
    - "repid-<product_uuid>--<price_uuid>" (multi-rate articles)
    - "custom-<product_uuid>--<price_uuid>" (free price amount in cents)

    :param donnees_post: QueryDict ou dict des données POST
    :param point_de_vente: instance PointDeVente (pour filtrer les produits autorisés)
    :return: liste de dicts {'product', 'price', 'quantite', 'prix_centimes', 'custom_amount_centimes', 'weight_amount'}
    """
    articles_extraits = PanierSerializer.extraire_articles_du_post(donnees_post)
    if not articles_extraits:
        return []

    # Charger tous les produits du PV en une seule requête (avec tarifs préchargés)
    # Memes tarifs que les tuiles (voir _tarifs_vendables_a_la_caisse) : un POST
    # force avec un autre tarif est donc refuse aussi.
    # / Load all POS products in one query. Same prices as the tiles.
    prix_euros_prefetch = Prefetch(
        "prices",
        queryset=_tarifs_vendables_a_la_caisse(),
        to_attr="prix_euros",
    )
    # Produits du PV : ceux avec methode_caisse (articles POS) OU categorie_article=ADHESION
    # Les adhesions n'ont pas forcement de methode_caisse (elles sont identifiees par categorie_article).
    # / POS products: those with methode_caisse (POS articles) OR categorie_article=ADHESION
    # Memberships don't necessarily have methode_caisse (identified by categorie_article).
    produits_du_pv = {
        str(p.uuid): p
        for p in point_de_vente.products.filter(
            Q(methode_caisse__isnull=False) | Q(categorie_article=Product.ADHESION)
        )
        .select_related("stock_inventaire")
        .prefetch_related(prix_euros_prefetch)
    }

    articles_panier = []
    for article_data in articles_extraits:
        uuid_str = article_data["uuid"]
        quantite = article_data["quantite"]
        price_uuid_str = article_data.get("price_uuid")
        custom_amount_centimes = article_data.get("custom_amount_centimes")
        weight_amount = article_data.get("weight_amount")

        # --- Articles BILLETTERIE : ID composite "{event_uuid}__{price_uuid}" ---
        # Le JS envoie repid-{event_uuid}__{price_uuid} pour les tuiles billet.
        # On sépare event UUID et price UUID, puis on charge le Product via la Price.
        # / BILLETTERIE articles: composite ID "{event_uuid}__{price_uuid}".
        # The JS sends repid-{event_uuid}__{price_uuid} for ticket tiles.
        # We split event UUID and price UUID, then load the Product via the Price.
        produit = None
        event_billet = None
        est_billet = False

        if "__" in uuid_str and point_de_vente.comportement == PointDeVente.BILLETTERIE:
            event_uuid_str, price_uuid_str_billet = uuid_str.split("__", 1)
            try:
                prix_billet = Price.objects.select_related("product").get(
                    uuid=price_uuid_str_billet,
                    publish=True,
                    asset__isnull=True,
                )
            except Price.DoesNotExist:
                logger.warning(
                    f"Price {price_uuid_str_billet} introuvable "
                    f"(billet PV {point_de_vente.name})"
                )
                continue
            produit = prix_billet.product
            price_uuid_str = str(prix_billet.uuid)
            est_billet = True
            # Retrouver l'event depuis l'UUID composite
            # / Find the event from the composite UUID
            event_billet = Event.objects.filter(uuid=event_uuid_str).first()
            # Prefetch les prix EUR du produit (necessaire pour la validation)
            # / Prefetch product's EUR prices (needed for validation)
            produit.prix_euros = list(
                produit.prices.filter(publish=True, asset__isnull=True).order_by(
                    "order"
                )
            )

        # --- Articles POS classiques : chercher par Product UUID ---
        # / Standard POS articles: look up by Product UUID
        if produit is None:
            produit = produits_du_pv.get(uuid_str)

        # --- Recharges : acceptees depuis TOUS les points de vente ---
        # Un produit de recharge du lieu est accepte meme s'il n'est pas dans
        # le M2M du PV (voir _produits_de_recharge_du_lieu). La vente reste
        # enregistree sur CE point de vente.
        # / Top-ups: accepted from EVERY POS, even outside the POS M2M.
        if produit is None:
            uuid_est_valide = True
            try:
                uuid_module.UUID(uuid_str)
            except ValueError:
                uuid_est_valide = False
            if uuid_est_valide:
                produit = _produits_de_recharge_du_lieu().filter(uuid=uuid_str).first()

        if produit is None:
            logger.warning(
                f"Produit {uuid_str} non trouvé dans le PV {point_de_vente.name}"
            )
            continue

        # Recharge temps desactivee : refuser un produit TM, meme dans un POST force.
        # Sinon il serait encaisse en euros sans crediter de temps.
        # / Time top-up disabled: reject a TM product, even in a forged POST.
        if produit.methode_caisse == Product.RECHARGE_TEMPS:
            logger.warning(
                f"Produit {produit.name} (recharge temps) refusé : fonction désactivée"
            )
            continue

        _retirer_les_tarifs_en_points_non_vendables(produit)

        if not produit.prix_euros:
            logger.warning(f"Produit {produit.name} n'a pas de tarif publié")
            continue

        # Si un price_uuid est fourni (multi-tarif), charger ce Prix spécifique
        # If a price_uuid is provided (multi-rate), load that specific Price
        if price_uuid_str:
            prix_obj = None
            for p in produit.prix_euros:
                if str(p.uuid) == price_uuid_str:
                    prix_obj = p
                    break
            if prix_obj is None:
                logger.warning(f"Prix {price_uuid_str} non trouvé pour {produit.name}")
                continue
        else:
            # Ancien format : premier prix EUR
            # Old format: first EUR price
            prix_obj = produit.prix_euros[0]

        # Valider le prix libre ou poids/mesure (custom_amount_centimes)
        # Pour le poids/mesure : le serveur recalcule le montant (quantite x prix de reference).
        # Pour le prix libre : le montant doit etre >= au minimum (prix de base).
        # Pour les autres tarifs : un montant custom est rejete.
        # / Validate free price or weight/volume (custom_amount_centimes)
        # Weight/volume: server recomputes the amount. Free price: amount >= minimum.
        # Other prices: a custom amount is rejected.
        if prix_obj.poids_mesure:
            # Poids/mesure : le serveur recalcule le montant lui-meme.
            # On ne fait jamais confiance au montant envoye par le JS :
            # un client modifie pourrait vendre 1 kg a 1 centime.
            # On part de la quantite saisie (weight_amount, en g ou en cl)
            # et du prix de reference du tarif (prix au kg ou au litre).
            # / Weight/volume: the server recomputes the amount itself and never
            # trusts the JS amount. Based on the entered quantity and the price per kg/L.
            quantite_saisie_est_valide = (
                weight_amount is not None and weight_amount > 0
            )
            if not quantite_saisie_est_valide:
                logger.warning(
                    f"Quantite poids/mesure absente ou invalide ({weight_amount}) "
                    f"pour {prix_obj.name} : article ignore"
                )
                continue

            montant_recalcule_centimes = _montant_poids_mesure_en_centimes(
                produit, prix_obj, weight_amount
            )

            # Un ecart avec le montant du JS n'est pas normal : on le trace.
            # / A gap with the JS amount is not normal: log it.
            montant_du_js_est_different = (
                custom_amount_centimes is not None
                and abs(custom_amount_centimes - montant_recalcule_centimes) > 1
            )
            if montant_du_js_est_different:
                logger.warning(
                    f"Montant poids/mesure du client ({custom_amount_centimes}) "
                    f"different du montant serveur ({montant_recalcule_centimes}) "
                    f"pour {prix_obj.name} : montant serveur retenu"
                )

            custom_amount_centimes = montant_recalcule_centimes

        elif custom_amount_centimes is not None:
            if prix_obj.free_price:
                # Prix libre : le montant doit etre >= au minimum
                # / Free price: amount must be >= minimum
                prix_minimum_centimes = int(round(prix_obj.prix * 100))
                if custom_amount_centimes < prix_minimum_centimes:
                    raise ValueError(
                        _(
                            "Montant libre (%(montant)s€) inférieur au minimum (%(minimum)s€)"
                        )
                        % {
                            "montant": f"{custom_amount_centimes / 100:.2f}",
                            "minimum": f"{prix_minimum_centimes / 100:.2f}",
                        }
                    )
            else:
                # Ni prix libre ni poids/mesure : rejeter le custom_amount
                # / Neither free price nor weight/volume: reject custom_amount
                logger.warning(f"Prix {prix_obj.name} n'accepte pas de montant custom")
                custom_amount_centimes = None

        # Le prix effectif : montant custom (prix libre) ou prix standard
        # Effective price: custom amount (free price) or standard price
        prix_en_centimes = custom_amount_centimes or int(round(prix_obj.prix * 100))

        # Un retour de consigne rend le prix du gobelet qu'il rembourse, jamais le sien
        # (D11). Sans consigne reliée, `_prix_de_la_consigne_remboursee_en_centimes`
        # lève une ValueError au message clair : l'appelant refuse la vente (400)
        # avant toute écriture.
        # / A deposit return gives back the cup's price. Without a link: ValueError,
        #   the caller refuses the sale before writing anything.
        if produit.methode_caisse == Product.RETOUR_CONSIGNE:
            prix_en_centimes = _prix_de_la_consigne_remboursee_en_centimes(produit)

        articles_panier.append(
            {
                "product": produit,
                "price": prix_obj,
                "quantite": quantite,
                "prix_centimes": prix_en_centimes,
                "custom_amount_centimes": custom_amount_centimes,
                "weight_amount": weight_amount,
                "est_billet": est_billet,
                "event": event_billet,
            }
        )

    return articles_panier


def _calculer_total_panier_centimes(articles_panier):
    """
    Calcule le total du panier en centimes.
    Calculates the cart total in centimes.

    :param articles_panier: liste de dicts retournée par _extraire_articles_du_panier()
    :return: total en centimes (int)
    """
    total_centimes = 0
    for article in articles_panier:
        total_centimes += article["prix_centimes"] * article["quantite"]
    return total_centimes


def _construire_recapitulatif_articles(articles_panier, prenom_client, nom_client):
    """
    Construit la liste d'articles pour l'ecran recapitulatif client.
    Chaque article a un texte adaptatif selon son type (recharge, adhesion, billet, vente).
    / Builds the article list for the client recap screen.
    Each article gets adaptive text based on its type (top-up, membership, ticket, sale).

    LOCALISATION : laboutik/views.py

    Utilise par identifier_client() pour les deux cas :
    - User identifie (carte avec user OU formulaire email)
    - Carte anonyme avec recharge seule (prenom_client = tag_id)
    / Used by identifier_client() for both cases:
    - Identified user (card with user OR email form)
    - Anonymous card with top-up only (prenom_client = tag_id)

    :param articles_panier: liste de dicts retournee par _extraire_articles_du_panier()
    :param prenom_client: prenom du client ou tag_id de la carte (str)
    :param nom_client: nom du client ou chaine vide (str)
    :return: liste de dicts {'description': str, 'prix_total_euros': float}
    """
    # Utilise la constante module METHODES_RECHARGE (ligne ~721)
    # / Uses the module-level METHODES_RECHARGE constant
    articles_pour_recapitulatif = []

    for article in articles_panier:
        produit = article["product"]
        prix_unitaire_euros = article["prix_centimes"] / 100
        quantite = article["quantite"]
        prix_total_euros = prix_unitaire_euros * quantite

        if (
            hasattr(produit, "methode_caisse")
            and produit.methode_caisse in METHODES_RECHARGE
        ):
            description = _("Recharge %(montant)s€ → carte de %(prenom)s") % {
                "montant": f"{prix_unitaire_euros:.2f}",
                "prenom": prenom_client,
            }
        elif produit.categorie_article == Product.ADHESION:
            description = _("%(nom_prix)s → rattachée à %(prenom)s %(nom)s") % {
                "nom_prix": article["price"].name,
                "prenom": prenom_client,
                "nom": nom_client.upper() if nom_client else "",
            }
        elif article.get("est_billet", False):
            event_name = article["event"].name if article.get("event") else "?"
            description = _("Billet %(nom)s — %(event)s") % {
                "nom": article["price"].name,
                "event": event_name,
            }
        else:
            description = f"{produit.name} × {quantite}"

        articles_pour_recapitulatif.append(
            {
                "description": description,
                "prix_total_euros": prix_total_euros,
            }
        )

    return articles_pour_recapitulatif


def _rendre_popup_paiement_client_identifie(
    request,
    point_de_vente,
    articles_panier,
    total_centimes,
    moyens_paiement_du_post,
    client_email,
    client_prenom,
    client_nom,
    client_solde,
    tag_id,
    panier_a_recharges,
    panier_a_adhesions,
    panier_a_billets,
):
    """
    Affiche la popup de paiement, une fois le client identifie.
    / Renders the payment popup once the client is identified.

    LOCALISATION : laboutik/views.py

    On reutilise la popup de la vente normale (hx_display_type_payment.html).
    Le mode « client_identifie » ajoute en haut le nom du client et le detail
    des articles. Les tuiles de paiement sont les memes que pour une vente
    normale (partial/_tuiles_paiement.html).
    / Reuses the normal-sale popup in "client_identifie" mode: client name
    and article recap on top, the same payment tiles below.

    Deux cas particuliers :
    - La carte a deja ete scannee (tag_id) : CASHLESS paie tout de suite
      avec cette carte. Pas de deuxieme scan, pas de popup.
    - Le panier est gratuit (ex : billet a 0 €) : un seul bouton VALIDER.
      Il n'y a rien a encaisser.
    / Two special cases: card already scanned (CASHLESS pays at once),
    free cart (a single VALIDATE button).

    Appelee par / Called by : PaiementViewSet.identifier_client()
    """
    # Les moyens de paiement sont recalcules par le serveur.
    # Si le point de vente est introuvable, on garde ceux recus du formulaire.
    # / Payment methods are recomputed server-side; fall back to the POST list.
    if point_de_vente is not None:
        moyens_paiement = _determiner_moyens_paiement(point_de_vente, articles_panier)
    else:
        moyens_paiement = moyens_paiement_du_post

    # Le panier est gratuit si le total vaut 0 et qu'il contient au moins un article.
    # Ce calcul est fait par le serveur, jamais lu depuis le formulaire.
    # / The cart is free when the total is 0 and it holds at least one item.
    panier_est_gratuit = total_centimes == 0 and len(articles_panier) > 0

    articles_pour_recapitulatif = _construire_recapitulatif_articles(
        articles_panier,
        client_prenom,
        client_nom,
    )

    # Solde affiche du client : en euros ; pour un panier en points, le solde de
    # la carte dans la monnaie du panier (ce qui dira si la carte peut payer).
    # / Shown client balance: euros; for a points cart, the card balance in
    #   the cart's currency.
    symbole_du_solde_client = CURRENCY_DATA["symbol"]
    try:
        monnaie_du_panier = _monnaie_du_panier(articles_panier)
    except ValueError:
        monnaie_du_panier = None
    if monnaie_du_panier is not None and tag_id:
        symbole_du_solde_client = monnaie_du_panier.name
        client_solde = 0
        carte_du_client = CarteCashless.objects.filter(tag_id=tag_id).first()
        wallet_de_la_carte = None
        if carte_du_client is not None:
            if carte_du_client.user is not None and carte_du_client.user.wallet is not None:
                wallet_de_la_carte = carte_du_client.user.wallet
            else:
                wallet_de_la_carte = carte_du_client.wallet_ephemere
        if wallet_de_la_carte is not None:
            client_solde = (
                WalletService.obtenir_solde(
                    wallet=wallet_de_la_carte, asset=monnaie_du_panier
                )
                / 100
            )

    context = {
        "client_identifie": True,
        "currency_data": _currency_data_du_panier(articles_panier),
        "symbole_du_solde_client": symbole_du_solde_client,
        "total": total_centimes / 100,
        "moyens_paiement": moyens_paiement,
        "moyens_paiement_csv": ",".join(moyens_paiement),
        # Tuile OFFRIR pour le gerant (adhesion, billet offerts).
        # / GIFT tile for the manager (gifted membership, ticket).
        "mode_gerant": _panier_peut_etre_offert(
            articles_panier, request.POST.get("tag_id_cm", "")
        ),
        "deposit_is_present": False,
        "comportement": "",
        "panier_a_recharges": panier_a_recharges,
        "panier_a_adhesions": panier_a_adhesions,
        "panier_a_billets": panier_a_billets,
        "panier_est_gratuit": panier_est_gratuit,
        "carte_deja_scannee": bool(tag_id),
        "user_email": client_email,
        "user_prenom": client_prenom,
        "user_nom": client_nom,
        "user_solde": client_solde,
        "tag_id": tag_id,
        "articles_pour_recapitulatif": articles_pour_recapitulatif,
        # Nouvelle cle a chaque affichage des moyens de paiement.
        # Voir _executer_avec_cle_idempotence().
        # / New key each time payment methods are shown.
        "cle_idempotence_paiement": uuid_module.uuid4(),
    }
    return render(request, "laboutik/partial/hx_display_type_payment.html", context)


def _determiner_moyens_paiement(point_de_vente, articles_panier=None):
    """
    Détermine les moyens de paiement disponibles selon la config du PV et le panier.
    Determines available payment methods based on PV config and cart contents.

    LOCALISATION : laboutik/views.py

    RÈGLE MÉTIER : si le panier contient des recharges euros (RE), le paiement NFC
    est interdit. Une recharge en monnaie locale ne peut pas être payée en cashless.
    Les recharges cadeau (RC) et temps (TM) sont gratuites — elles ne bloquent pas le NFC.
    BUSINESS RULE: if the cart contains euro top-ups (RE), NFC payment is forbidden.
    A local currency top-up cannot be paid with cashless.
    Gift (RC) and time (TM) top-ups are free — they don't block NFC.

    RÈGLE MÉTIER : un panier en points ou en temps se paie uniquement par NFC.
    BUSINESS RULE: a points or time cart is paid only by NFC.

    :param point_de_vente: instance PointDeVente
    :param articles_panier: liste de dicts retournée par _extraire_articles_du_panier() (optionnel)
    :return: liste de codes moyens de paiement (ex: ["nfc", "espece", "carte_bancaire"])
    """
    # Un panier en points ou en temps se paie uniquement avec la carte du client :
    # c'est elle qui porte les points.
    # / A points or time cart is paid only with the customer's card.
    if articles_panier and _panier_est_en_points(articles_panier):
        return ["nfc"]

    moyens = []

    # NFC interdit uniquement si le panier contient des recharges PAYANTES (RE).
    # Les recharges gratuites (RC/TM) ne bloquent pas le NFC — elles sont auto-creditees.
    # / NFC forbidden only if cart contains PAID top-ups (RE).
    # Free top-ups (RC/TM) don't block NFC — they are auto-credited.
    panier_a_recharges_payantes = (
        articles_panier and _panier_contient_recharges_payantes(articles_panier)
    )
    if not panier_a_recharges_payantes:
        moyens.append("nfc")

    if point_de_vente.accepte_especes:
        moyens.append("espece")

    # Un retour de consigne rend de l'argent : on ne le rend qu'en especes ou sur la
    # carte du client. Ni carte bancaire ni cheque, quelle que soit la configuration du
    # point de vente — on ne rembourse pas un euro sur un terminal de paiement, et on ne
    # fait pas un cheque pour une consigne. Meme regle qu'en V1
    # (`LaBoutik/webview/static/webview/js/points_ventes.js` : 'espece|nfc').
    # / A deposit return gives money back: cash or the customer's card only. Never card
    #   terminal nor check, whatever the POS accepts. Same rule as V1.
    if articles_panier and _panier_contient_retour_consigne(articles_panier):
        # Le cashless n'est propose que si la monnaie a crediter est utilisable. Sinon
        # le paiement echouerait a coup sur, apres que le client a presente sa carte :
        # un bouton qui mene a un refus certain n'a pas a s'afficher.
        # / CASHLESS is offered only if the currency to credit is usable: otherwise the
        #   payment would fail for certain, after the customer tapped their card.
        asset_a_crediter, _raison_du_refus = _asset_de_retour_consigne(articles_panier)
        if asset_a_crediter is None and "nfc" in moyens:
            moyens.remove("nfc")
        return moyens

    if point_de_vente.accepte_carte_bancaire:
        moyens.append("carte_bancaire")

    if point_de_vente.accepte_cheque:
        moyens.append("CH")

    return moyens


def _valider_stock_panier(articles_panier):
    """
    Verifie que chaque produit du panier a un stock suffisant si son Stock
    interdit la vente hors stock (autoriser_vente_hors_stock=False).
    A appeler AVANT le transaction.atomic() de _creer_lignes_articles.
    / Checks that each cart product has enough stock if Stock blocks out-of-stock sale.
    Must be called BEFORE _creer_lignes_articles' transaction.atomic().

    LOCALISATION : laboutik/views.py

    IMPORTANT : on additionne TOUTES les lignes d'un meme produit.
    Un produit peut apparaitre sur plusieurs lignes du panier :
    - vrac : chaque saisie au pave cree une ligne (100g, puis encore 100g) ;
    - plusieurs tarifs du meme produit (ex : 25cl et 50cl sur le meme fut).
    Avant, chaque ligne etait comparee seule au stock : 100g + 100g passaient
    sur un stock de 100g, meme quand la vente hors stock etait interdite.
    / IMPORTANT: all lines of the same product are summed before comparing.

    FLUX :
    1. Pour chaque ligne, calcule la quantite demandee et l'ajoute au total du produit.
    2. Pour chaque produit, compare le total au stock.

    :param articles_panier: liste de dicts retournee par _extraire_articles_du_panier()
    :return: liste de dicts {name, demande, disponible, unite}, un par produit en defaut.
             Liste vide = panier OK.
    """
    # --- 1. Total demande par produit ---
    # Cle : uuid du produit. Valeur : {"stock": Stock, "name": str, "demande": int}
    # / Key: product uuid. Value: stock, name and total requested quantity.
    total_demande_par_produit = {}

    for article in articles_panier:
        produit = article["product"]

        # Un retour de consigne n'est jamais bloqué par le stock : le client en
        # RAPPORTE un. Lui refuser sa consigne parce qu'il ne reste plus de gobelets
        # reviendrait à garder son argent.
        # / A deposit return is never blocked by stock: the customer is bringing one IN.
        if produit.methode_caisse == Product.RETOUR_CONSIGNE:
            continue

        try:
            stock = produit.stock_inventaire
        except Stock.DoesNotExist:
            # Pas de gestion de stock pour ce produit, rien a verifier
            # / No stock management for this product, nothing to check
            continue

        if stock.autoriser_vente_hors_stock:
            # Vente hors stock autorisee : aucun blocage en amont
            # / Out-of-stock sale allowed: no upstream blocking
            continue

        # Calcule la quantite reellement demandee : poids/mesure ou contenance fixe
        # (meme regle que la decrementation dans _creer_lignes_articles)
        # / Compute actually requested quantity: weight/measure or fixed contenance
        weight_amount = article.get("weight_amount")
        if weight_amount:
            quantite_demandee = weight_amount  # ex : 350g pour les cacahuetes
        else:
            contenance = article["price"].contenance or 1
            quantite_demandee = article["quantite"] * contenance

        if produit.uuid not in total_demande_par_produit:
            total_demande_par_produit[produit.uuid] = {
                "stock": stock,
                "name": produit.name,
                "demande": 0,
            }
        total_demande_par_produit[produit.uuid]["demande"] += quantite_demandee

    # --- 2. Comparer chaque total au stock ---
    # / Compare each total to the stock
    erreurs = []
    for total_du_produit in total_demande_par_produit.values():
        stock = total_du_produit["stock"]
        if total_du_produit["demande"] > stock.quantite:
            erreurs.append(
                {
                    "name": total_du_produit["name"],
                    "demande": total_du_produit["demande"],
                    "disponible": stock.quantite,
                    "unite": stock.unite,
                }
            )

    return erreurs


def _formater_erreurs_stock(erreurs):
    """
    Formate la liste d'erreurs stock en message lisible pour le caissier.
    Utilise par les vues de paiement quand _valider_stock_panier renvoie des erreurs.
    / Formats stock error list into a readable message for the cashier.

    LOCALISATION : laboutik/views.py

    Une ligne par produit : "Biere : 3 dans le panier, 2 en stock".
    On ecrit "dans le panier" (et pas "demande") : c'est le TOTAL du panier
    pour ce produit, toutes lignes confondues. Les quantites sont lisibles
    (1.5 L, 800 g) grace a _formater_stock_lisible.
    Le retour a la ligne est affiche par .alerte-messages-texte (white-space: pre-line).
    / One line per product: "Beer: 3 in the cart, 2 in stock".

    :param erreurs: liste de dicts {name, demande, disponible, unite}
    :return: str formatee, prete pour msg_content de hx_messages.html
    """
    lignes_du_message = [str(_("Stock insuffisant — vente refusée."))]
    for erreur in erreurs:
        lignes_du_message.append(
            _("%(nom)s : %(au_panier)s dans le panier, %(en_stock)s en stock")
            % {
                "nom": erreur["name"],
                "au_panier": _formater_stock_lisible(erreur["demande"], erreur["unite"]),
                "en_stock": _formater_stock_lisible(
                    erreur["disponible"], erreur["unite"]
                ),
            }
        )
    return "\n".join(lignes_du_message)


def _taux_tva_de_la_ligne_de_caisse(produit, methode_db):
    """
    Le taux de TVA d'une ligne écrite par la caisse, en pour cent (Decimal).
    / The VAT rate of a line written by the register, in percent (Decimal).

    LOCALISATION : laboutik/views.py

    Le service de vente écrit le taux qu'on lui passe (`ajouter_article`) : la caisse
    le calcule ici, avec la même règle que la TVA par défaut d'une ligne
    (`LigneArticle._compute_default_vat`), plus deux règles (points 2 et 3) :
    1. ligne offerte (FREE) ou en points / temps (NON_MONETAIRE) : 0, ce n'est pas une
       vente en argent ; ligne payée en jetons cadeau (LOCAL_GIFT) : 0, c'est une vente
       ordinaire, hors TVA (D8 bis : le jeton dépensé solde la dette du lieu) ;
    2. recharge (RE, RC) : 0. Une recharge est une dette envers le porteur de la carte,
       pas une vente taxée (D10) ;
    3. retour de consigne : le taux du produit consigne qu'il rembourse (le gobelet,
       `Product.consigne_remboursee`) : le retour annule la vente du gobelet, TVA
       comprise (D11) ;
    4. sinon : le taux du produit, ou à défaut le taux par défaut du lieu
       (`Configuration.vat_taxe`), jamais celui de la catégorie.
    / 0 for offered, points, gift tokens, top-ups; the cup's rate for a deposit return;
    otherwise the product's rate, else the venue default.

    Sert aussi la tireuse (controlvanne/billing.py), le paiement QR, l'API v2.
    / Also used by the tap, the QR payment and API v2.

    :param produit: Product vendu
    :param methode_db: PaymentMethod de la ligne (valeur en base, ex. "CA", "NA")
    :return: Decimal
    """
    ligne_hors_tva_par_son_moyen = methode_db in (
        PaymentMethod.FREE,
        PaymentMethod.NON_MONETAIRE,
        PaymentMethod.LOCAL_GIFT,
    )
    if ligne_hors_tva_par_son_moyen:
        return Decimal("0")

    if produit.methode_caisse in METHODES_RECHARGE:
        return Decimal("0")

    produit_qui_porte_la_tva = produit
    if produit.methode_caisse == Product.RETOUR_CONSIGNE:
        # `_extraire_articles_du_panier` a déjà refusé un retour sans consigne reliée.
        # / A return without a linked deposit was already refused upstream.
        produit_qui_porte_la_tva = produit.consigne_remboursee

    if produit_qui_porte_la_tva.tva is not None:
        return Decimal(produit_qui_porte_la_tva.tva.tva_rate)
    return Decimal(Configuration.get_solo().vat_taxe)


def _creer_lignes_articles(
    articles_panier,
    code_methode_paiement,
    asset_uuid=None,
    carte=None,
    wallet=None,
    uuid_transaction=None,
    point_de_vente=None,
    vente=None,
):
    """
    Crée ProductSold, PriceSold et LigneArticle pour chaque article du panier.
    Creates ProductSold, PriceSold and LigneArticle for each article in the cart.

    LOCALISATION : laboutik/views.py

    Cette fonction est appelée dans un bloc transaction.atomic() par les fonctions
    de paiement (_payer_par_carte_ou_cheque, _payer_en_especes, _rembourser_consigne_par_nfc,
    _executer_recharges, payer_commande).
    This function is called inside a transaction.atomic() block by the payment functions.

    DEUX FAÇONS D'ÉCRIRE UNE LIGNE :
    - `vente` donnée : c'est le cas de tous les chemins de la caisse. La ligne est un
      article de la vente, écrit par le service de vente (`ajouter_article`) avec ses
      montants entiers, et avec ses champs historiques (moyen, statut, carte,
      identifiant de paiement…). Le HT vient du service, la boucle HMAC ne le
      recalcule pas. L'appelant ajoute les règlements et encaisse la vente.
    - `vente` absente : plus aucun chemin de la caisse ne l'utilise. Seuls des tests
      existants appellent encore cette fonction sans vente (stock, billetterie,
      offerts). La ligne est alors créée directement (`LigneArticle.objects.create`),
      et son HT est calculé par la boucle HMAC.
      TODO : retirer cette branche avec l'ancien modèle (fiche H), et réécrire ces
      tests pour qu'ils passent une vente.
    / Two ways: with a sale (every register path), or a direct create, now used only by
    existing tests calling this function directly. TODO: remove that branch with the
    old model (sheet H) and rewrite those tests to pass a sale.

    :param articles_panier: liste de dicts retournée par _extraire_articles_du_panier()
    :param code_methode_paiement: code du moyen de paiement ("carte_bancaire", "espece", "CH", "nfc", "gift")
    :param asset_uuid: UUID de l'asset fedow_core (NFC uniquement, None pour espèces/CB)
    :param carte: CarteCashless (NFC uniquement, None pour espèces/CB)
    :param wallet: Wallet du client (NFC uniquement, None pour espèces/CB)
    :param uuid_transaction: identifiant du paiement, posé sur chaque ligne
    :param point_de_vente: PointDeVente d'origine (nullable, pour ventilation CA par PV)
    :param vente: la `Vente` EN_ATTENTE qui reçoit les articles, ou None (voir plus haut)
    :return: tuple (liste de LigneArticle créées, produits dont le stock est négatif)
    """
    methode_db = MAPPING_CODES_PAIEMENT.get(
        code_methode_paiement, PaymentMethod.UNKNOWN
    )

    # MODE ECOLE DESACTIVE — toute vente est une vente reelle.
    # / TRAINING MODE DISABLED — every sale is a real sale.
    #
    # Le mode ecole (LNE exigence 5) marquait ici les ventes d'une origine
    # distincte, pour les exclure des rapports comptables. Cette origine n'existe
    # pas dans `SaleOrigin` : l'activer levait une `AttributeError` et bloquait
    # tout encaissement au point de vente.
    # Le champ `mode_ecole` reste en base mais n'est plus propose dans l'admin.
    # Voir CHANGELOG/2026-07-22-mode-ecole-desactive.md.
    # / Training mode tagged sales with a separate origin to keep them out of the
    # accounting reports. That origin does not exist in SaleOrigin: enabling the
    # mode raised an AttributeError and blocked every sale at the register.
    sale_origin_pour_ligne = SaleOrigin.LABOUTIK

    lignes_creees = []

    # Accumulateur des produits dont le stock a été décrémenté.
    # On broadcastera la mise à jour via WebSocket après le commit.
    # / Accumulator of products whose stock was decremented.
    # We'll broadcast the update via WebSocket after commit.
    produits_stock_mis_a_jour = []

    # Accumulateur des produits dont le stock vient de passer en negatif.
    # Affiche en fin de paiement sur l'ecran de validation (give-back-box orange).
    # Ne contient que les produits avec autoriser_vente_hors_stock=True
    # (sinon la vente aurait ete bloquee en amont par _valider_stock_panier).
    # / Accumulator of products whose stock just went negative.
    # Shown at end of payment on validation screen (orange give-back-box).
    # Only contains products with autoriser_vente_hors_stock=True
    # (otherwise the sale would have been blocked upstream).
    produits_stock_negatif = []

    for article in articles_panier:
        produit = article["product"]
        prix_obj = article["price"]
        quantite = article["quantite"]
        prix_centimes = article["prix_centimes"]
        weight_amount = article.get("weight_amount")

        # ProductSold : snapshot du produit au moment de la vente
        # ProductSold: product snapshot at the time of sale
        product_sold, _ = ProductSold.objects.get_or_create(
            product=produit,
            event=None,
            defaults={"categorie_article": produit.categorie_article},
        )

        # PriceSold : snapshot du prix au moment de la vente
        # PriceSold: price snapshot at the time of sale
        price_sold, _ = PriceSold.objects.get_or_create(
            productsold=product_sold,
            price=prix_obj,
            defaults={"prix": prix_obj.prix},
        )

        # Les champs historiques de la ligne (moyen, statut, carte, identifiant de
        # paiement…) : les anciens rapports les lisent jusqu'à la fiche H.
        # / The line's historical fields: old reports read them until sheet H.
        champs_historiques_de_la_ligne = {
            "sale_origin": sale_origin_pour_ligne,
            "payment_method": methode_db,
            "status": LigneArticle.VALID,
            "uuid_transaction": uuid_transaction,
            "point_de_vente": point_de_vente,
            # Champs NFC (optionnels, None pour espèces/CB)
            # NFC fields (optional, None for cash/CC)
            "asset": asset_uuid,
            "carte": carte,
            "wallet": wallet,
            "weight_quantity": weight_amount,
        }

        if vente is None:
            # Ligne sans vente : seuls des tests existants appellent encore cette
            # fonction sans vente (stock, billetterie, offerts).
            # TODO : retirer cette branche avec l'ancien modèle (fiche H).
            # / Line without a sale: only existing tests still call this without a
            # sale. TODO: remove this branch with the old model (sheet H).
            ligne = LigneArticle.objects.create(
                pricesold=price_sold,
                qty=quantite,
                amount=prix_centimes,
                **champs_historiques_de_la_ligne,
            )
        else:
            # Le service de vente accepte des types exacts seulement : des centimes
            # `int`, une quantité et un taux `int` ou `Decimal`, jamais un `float` ni
            # un texte (ValueError sinon). Les valeurs du panier sont converties ici,
            # explicitement.
            # / The sale service takes exact types only: converted here, explicitly.
            quantite_vendue = int(quantite)
            prix_unitaire_en_centimes = int(prix_centimes)
            prix_achat_en_centimes = int(produit.prix_achat)

            # Retour de consigne : le coût d'achat est celui du gobelet rendu
            # (`consigne_remboursee`), jamais celui du produit de retour. Il est passé
            # en NÉGATIF, comme le prix de la ligne (prix négatif, quantité positive) :
            # un gobelet rendu retire son coût de la marge (D21). Un gobelet sans prix
            # d'achat (0) donne 0 : le coût reste inconnu, comme pour tout article.
            # `_extraire_articles_du_panier` a déjà refusé un retour sans consigne reliée.
            # / Deposit return: the returned cup's purchase cost, passed NEGATIVE like
            #   the line's price; a returned cup removes its cost from the margin.
            if produit.methode_caisse == Product.RETOUR_CONSIGNE:
                produit_du_gobelet_rendu = produit.consigne_remboursee
                prix_achat_en_centimes = -int(produit_du_gobelet_rendu.prix_achat)

            # Vente au poids ou au volume : la ligne garde qty = 1 et le poids dans
            # `weight_quantity` (anciens lecteurs). Le coût d'achat, lui, porte sur la
            # quantité réellement servie, dans l'unité du prix d'achat (kg, L) :
            # 350 g → 0,350 kg.
            # / Weight/volume sale: qty stays 1; the cost is on the real served quantity.
            vente_au_poids = bool(weight_amount) and prix_obj.poids_mesure
            if vente_au_poids:
                quantite_reellement_servie = (
                    Decimal(weight_amount)
                    / _diviseur_de_la_quantite_saisie(produit)
                    * Decimal(quantite_vendue)
                )
            else:
                quantite_reellement_servie = None

            # OFFRIR (mode gérant) et recharge cadeau : l'article est entièrement
            # offert. Le service pose la part offerte et ajoute le règlement FREE.
            # / GIFT and gift top-up: fully offered; the service adds the FREE payment.
            article_offert_en_totalite = methode_db == PaymentMethod.FREE

            ligne = ajouter_article(
                vente,
                pricesold=price_sold,
                quantite=quantite_vendue,
                prix_unitaire=prix_unitaire_en_centimes,
                taux_tva=_taux_tva_de_la_ligne_de_caisse(produit, methode_db),
                prix_achat=prix_achat_en_centimes,
                offert_en_totalite=article_offert_en_totalite,
                quantite_pour_cout=quantite_reellement_servie,
                **champs_historiques_de_la_ligne,
            )
        # --- Décrémentation stock inventaire ---
        # Si le produit a un Stock lié, on décrémente automatiquement.
        # Après décrémentation, on relit le stock depuis la DB
        # (F() ne met pas à jour l'instance en mémoire).
        # / If the product has a linked Stock, auto-decrement.
        # After decrement, re-read stock from DB (F() doesn't update in-memory instance).
        try:
            stock_du_produit = produit.stock_inventaire
        except Stock.DoesNotExist:
            # Pas de gestion de stock pour ce produit — comportement normal
            # / No stock management for this product — normal behavior
            stock_du_produit = None

        # Un retour de consigne ne sort rien du stock : le gobelet REVIENT. Décrémenter
        # ici retirerait un gobelet de l'inventaire au moment même où le client en
        # rapporte un.
        # / A deposit return takes nothing out of stock: the cup COMES BACK.
        if produit.methode_caisse == Product.RETOUR_CONSIGNE:
            stock_du_produit = None

        if stock_du_produit is not None:
            if weight_amount:
                # Poids/mesure : la quantite saisie par le caissier remplace contenance x qty.
                # On décrémente la quantité saisie (ex: 350g), pas la contenance fixe.
                # / Weight/volume: cashier's entered quantity replaces contenance x qty.
                # We decrement the entered quantity (e.g. 350g), not the fixed contenance.
                stock_devenu_negatif = StockService.decrementer_pour_vente(
                    stock=stock_du_produit,
                    contenance=weight_amount,
                    qty=1,
                    ligne_article=ligne,
                )
            else:
                # Tarif classique : contenance fixe x quantite
                # / Standard price: fixed contenance x quantity
                stock_devenu_negatif = StockService.decrementer_pour_vente(
                    stock=stock_du_produit,
                    contenance=prix_obj.contenance,
                    qty=quantite,
                    ligne_article=ligne,
                )

            # Relire le stock depuis la DB pour avoir la quantité à jour
            # / Re-read stock from DB to get updated quantity
            stock_du_produit.refresh_from_db()

            # Si le stock vient de passer en negatif, prevenir le caissier
            # via une alerte sur l'ecran de validation de la vente.
            # / If stock just went negative, warn the cashier via an alert
            # on the sale validation screen.
            if stock_devenu_negatif:
                produits_stock_negatif.append(
                    {
                        "name": produit.name,
                        "quantite": stock_du_produit.quantite,
                        "unite": stock_du_produit.unite,
                    }
                )

            # Données du badge : même fonction pour tous les chemins (wsocket/broadcast.py)
            # / Badge data: same function for every path
            produits_stock_mis_a_jour.append(donnees_badge_stock(stock_du_produit))

        lignes_creees.append(ligne)

    # --- Chainage HMAC (conformite LNE exigence 8) ---
    # Calcule le total HT et le HMAC pour chaque ligne creee.
    # Le HMAC est chaine avec la ligne precedente.
    # / HMAC chaining (LNE compliance req. 8).
    # Computes HT and HMAC for each created line.
    config_laboutik = LaboutikConfiguration.get_solo()
    cle_hmac = config_laboutik.get_or_create_hmac_key()

    # Determiner le sale_origin pour la chaine HMAC
    # / Determine sale_origin for HMAC chain
    sale_origin_pour_chaine = SaleOrigin.LABOUTIK
    if lignes_creees:
        sale_origin_pour_chaine = lignes_creees[0].sale_origin

    previous_hmac_value = obtenir_previous_hmac(sale_origin=sale_origin_pour_chaine)

    for ligne_a_chainer in lignes_creees:
        if vente is None:
            # Ligne sans vente (appels directs de tests existants seulement).
            # TODO : retirer ce calcul avec la branche sans vente (fiche H).
            # / Line without a sale (direct test calls only). TODO: remove with the
            # no-sale branch (sheet H).
            # Calculer le HT (donnee elementaire LNE exigence 3)
            # / Compute HT (LNE req. 3 elementary data)
            # Le HT porte sur le TTC de la LIGNE (prix unitaire x quantite), pas sur
            # un seul article. Arrondi comme montant_ttc_centimes() des rapports
            # (0,5 -> 1, comme Round() de PostgreSQL).
            # / HT is computed on the LINE total (unit price x qty), not one item.
            ttc_de_la_ligne_centimes = int(
                Decimal(ligne_a_chainer.amount * ligne_a_chainer.qty).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            ligne_a_chainer.total_ht = calculer_total_ht(
                ttc_de_la_ligne_centimes, ligne_a_chainer.vat
            )

            # Chainer le HMAC avec la ligne precedente
            # / Chain HMAC with previous line
            ligne_a_chainer.previous_hmac = previous_hmac_value
            ligne_a_chainer.hmac_hash = calculer_hmac(
                ligne_a_chainer, cle_hmac, previous_hmac_value
            )
            ligne_a_chainer.save(
                update_fields=["total_ht", "hmac_hash", "previous_hmac"]
            )
        else:
            # Ligne écrite par le service de vente : son HT est DÉJÀ juste (arrondi
            # demi vers le haut, HT + TVA = net). On ne le recalcule PAS :
            # `calculer_total_ht` arrondit au pair (111 c à 20 % donnerait 92 au lieu
            # de 93). L'empreinte est écrite par `.update()`, jamais par un second
            # `save()` (qui relancerait la machine à statuts de la ligne).
            # / Written by the sale service: its HT is already right, NOT recomputed.
            #   The fingerprint is written by .update(), never by a second save().
            ligne_a_chainer.previous_hmac = previous_hmac_value
            ligne_a_chainer.hmac_hash = calculer_hmac(
                ligne_a_chainer, cle_hmac, previous_hmac_value
            )
            LigneArticle.objects.filter(pk=ligne_a_chainer.pk).update(
                hmac_hash=ligne_a_chainer.hmac_hash,
                previous_hmac=ligne_a_chainer.previous_hmac,
            )

        previous_hmac_value = ligne_a_chainer.hmac_hash

    # --- Broadcast WebSocket des badges stock mis à jour ---
    # on_commit() : le broadcast ne s'exécute qu'après le commit de la transaction.
    # Si la transaction rollback, le broadcast n'est jamais envoyé.
    # / WebSocket broadcast of updated stock badges.
    # on_commit(): broadcast only runs after transaction commit.
    if produits_stock_mis_a_jour:
        from django.db import transaction
        from wsocket.broadcast import broadcast_stock_update

        # Dédupliquer par product_uuid : ne garder que le dernier état
        # (si le panier contient 5x Biere, on a 5 entrées pour le même produit
        # mais seul l'état final compte pour l'affichage)
        # / Deduplicate by product_uuid: keep only the last state
        donnees_par_produit = {}
        for donnee in produits_stock_mis_a_jour:
            donnees_par_produit[donnee["product_uuid"]] = donnee
        donnees_a_broadcaster = list(donnees_par_produit.values())

        transaction.on_commit(lambda: broadcast_stock_update(donnees_a_broadcaster))

    return lignes_creees, produits_stock_negatif


def _creer_lignes_articles_cascade(
    lignes_pre_calculees,
    vente,
    carte=None,
    carte_complement=None,
    wallet=None,
    uuid_transaction=None,
    point_de_vente=None,
):
    """
    Crée ProductSold, PriceSold et N LigneArticle par article (1 par asset débité).
    Creates ProductSold, PriceSold and N LigneArticle per article (1 per debited asset).

    LOCALISATION : laboutik/views.py

    Version « cascade » de _creer_lignes_articles().
    Un article à 4€ payé 1€ TNF + 3€ TLF produit 2 LigneArticle
    avec qty partielle proportionnelle au montant.
    / Cascade version of _creer_lignes_articles().
    A 4€ article paid 1€ TNF + 3€ TLF produces 2 LigneArticle
    with partial qty proportional to the amount.

    CHAQUE PART EST UN ARTICLE DE LA VENTE :
    Elle est écrite par le service de vente (`ajouter_article`) avec ses champs
    historiques d'aujourd'hui (prix unitaire, quantité partielle, moyen, carte…). Son
    total catalogue est l'argent RÉEL de la part (3ᵉ élément du tuple), jamais
    recalculé depuis la quantité partielle. Une part payée en jetons cadeau (LG) est
    une vente ordinaire, rien d'offert, au taux de TVA 0 (D8 bis : le jeton dépensé
    solde la dette du lieu envers le porteur). Le HT vient du service, la boucle HMAC
    ne le recalcule pas. L'appelant écrit les règlements et encaisse la vente.
    Appelants : paiement NFC seul, complément espèces / CB, 2ᵉ carte.
    / Each part is an item of the sale, written by the sale service (the part's real
    money as catalogue total; a token part is an ordinary sale at 0 % VAT). The caller
    writes the payments and settles the sale.

    :param lignes_pre_calculees: liste de tuples
        (article_dict, asset_ou_none, amount_centimes, payment_method_code)
    :param carte: CarteCashless principale (1ère carte NFC)
    :param carte_complement: CarteCashless de complément (2ème carte, Task 7)
    :param wallet: Wallet du client (1ère carte)
    :param uuid_transaction: UUID partagé par toutes les lignes du paiement
    :param point_de_vente: PointDeVente d'origine (ventilation CA par PV)
    :param vente: la `Vente` EN_ATTENTE qui reçoit les parts (obligatoire)
    :return: liste de toutes les LigneArticle créées
    """
    # --- MODE ECOLE DESACTIVE : toute vente est une vente reelle ---
    # / TRAINING MODE DISABLED: every sale is a real sale
    # Meme raison qu'en amont dans ce fichier : l'origine que le mode ecole
    # utilisait n'existe pas dans `SaleOrigin`.
    # / Same reason as earlier in this file: the origin training mode used does
    # not exist in SaleOrigin.
    sale_origin_pour_ligne = SaleOrigin.LABOUTIK

    # ------------------------------------------------------------------ #
    # Étape 1 : Regrouper les lignes par article (clé = id(article_dict))
    # / Step 1: Group lines by article (key = id(article_dict))
    # ------------------------------------------------------------------ #
    # On utilise id() car le même dict Python revient plusieurs fois
    # dans lignes_pre_calculees quand un article est splitté sur N assets.
    # / We use id() because the same Python dict appears multiple times
    # in lignes_pre_calculees when an article is split across N assets.
    from collections import OrderedDict

    groupes_par_article = OrderedDict()
    for tuple_ligne in lignes_pre_calculees:
        article_dict, asset_ou_none, amount_centimes, payment_method_code = tuple_ligne
        cle_groupe = id(article_dict)
        if cle_groupe not in groupes_par_article:
            groupes_par_article[cle_groupe] = {
                "article_dict": article_dict,
                "lignes": [],
            }
        groupes_par_article[cle_groupe]["lignes"].append(
            {
                "asset_ou_none": asset_ou_none,
                "amount_centimes": amount_centimes,
                "payment_method_code": payment_method_code,
            }
        )

    toutes_les_lignes_creees = []

    # Accumulateur pour les mises à jour stock (broadcast WebSocket).
    # / Accumulator for stock updates (WebSocket broadcast).
    produits_stock_mis_a_jour = []

    # Accumulateur des produits passes en stock negatif (alerte ecran de validation).
    # / Accumulator of products with negative stock (validation screen alert).
    produits_stock_negatif = []

    # ------------------------------------------------------------------ #
    # Étape 2 : Pour chaque article, créer ProductSold + PriceSold + N LigneArticle
    # / Step 2: For each article, create ProductSold + PriceSold + N LigneArticle
    # ------------------------------------------------------------------ #
    for cle_groupe, groupe in groupes_par_article.items():
        article_dict = groupe["article_dict"]
        lignes_du_groupe = groupe["lignes"]

        produit = article_dict["product"]
        prix_obj = article_dict["price"]
        quantite = article_dict["quantite"]
        prix_centimes = article_dict["prix_centimes"]
        weight_amount = article_dict.get("weight_amount")

        # ProductSold : snapshot du produit au moment de la vente
        # ProductSold: product snapshot at the time of sale
        product_sold, _ = ProductSold.objects.get_or_create(
            product=produit,
            event=None,
            defaults={"categorie_article": produit.categorie_article},
        )

        # PriceSold : snapshot du prix au moment de la vente
        # PriceSold: price snapshot at the time of sale
        price_sold, _ = PriceSold.objects.get_or_create(
            productsold=product_sold,
            price=prix_obj,
            defaults={"prix": prix_obj.prix},
        )

        # ---------------------------------------------------------- #
        # Calculer les qty partielles via _calculer_qty_partielles()
        # / Compute partial qty via _calculer_qty_partielles()
        # ---------------------------------------------------------- #
        lignes_pour_calcul = [
            {"amount_centimes": ligne["amount_centimes"]} for ligne in lignes_du_groupe
        ]
        lignes_avec_qty = _calculer_qty_partielles(
            lignes_pour_calcul, prix_centimes, quantite
        )

        # ---------------------------------------------------------- #
        # Créer N LigneArticle (1 par tuple du groupe)
        # / Create N LigneArticle (1 per tuple in the group)
        # ---------------------------------------------------------- #
        premiere_ligne_du_groupe = None

        for i, ligne_info in enumerate(lignes_du_groupe):
            asset_ou_none = ligne_info["asset_ou_none"]
            amount_centimes = ligne_info["amount_centimes"]
            payment_method_code = ligne_info["payment_method_code"]
            qty_partielle = lignes_avec_qty[i]["qty"]

            # Déterminer l'UUID de l'asset (None pour espèces/CB)
            # / Determine asset UUID (None for cash/CC)
            asset_uuid = None
            if asset_ou_none is not None:
                # Asset local = objet fedow_core (`.pk` = uuid). Asset legacy distant (FED / TLF
                # fédéré débité via Fedow) = uuid déjà résolu (pas d'objet local). On accepte les deux.
                # / Local asset = fedow_core object (`.pk`). Remote legacy asset = already-resolved uuid.
                asset_uuid = (
                    asset_ou_none.pk if hasattr(asset_ou_none, "pk") else asset_ou_none
                )

            # Toujours associer la carte principale à la LigneArticle.
            # La carte identifie le client pour le paiement (même pour les
            # lignes complémentaires espèces/CB, la carte a été scannée).
            # Pour la 2ème carte NFC, l'appelant passe les lignes des 2 cartes
            # séparément avec carte=carte1 et carte_complement n'est pas utilisée
            # ici (elle pourrait servir à un futur enrichissement).
            # / Always associate the primary card with the LigneArticle.
            # The card identifies the client for the payment (even for
            # cash/CC complement lines, the card was scanned).
            carte_pour_cette_ligne = carte

            # amount = prix UNITAIRE (en centimes), PAS le montant total de la part.
            # Convention unifiée avec le chemin simple (_creer_lignes_articles) et avec
            # LigneArticle.total = amount × qty : le total de ligne = prix_unitaire × qty.
            # La part en argent est portée par qty (= montant_part / prix_unitaire),
            # calculée par _calculer_qty_partielles. Stocker l'argent ici comptait la
            # quantité deux fois à l'affichage (bug B : 3 vins → 45 € au lieu de 15 €).
            # / amount = UNIT price (cents), NOT the part's total money. Unified with the
            # simple path and LigneArticle.total = amount × qty. Storing money here
            # double-counted the quantity in the display (bug B: 45 € instead of 15 €).
            champs_historiques_de_la_part = {
                "sale_origin": sale_origin_pour_ligne,
                "payment_method": payment_method_code,
                "status": LigneArticle.VALID,
                "uuid_transaction": uuid_transaction,
                "point_de_vente": point_de_vente,
                # Champs NFC (optionnels, None pour espèces/CB)
                # NFC fields (optional, None for cash/CC)
                "asset": asset_uuid,
                "carte": carte_pour_cette_ligne,
                "wallet": wallet,
                # weight_quantity identique sur toutes les lignes d'un même article
                # / weight_quantity same on all lines of the same article
                "weight_quantity": weight_amount,
            }

            # Le service de vente accepte des types exacts seulement : des centimes
            # `int`, une quantité et un taux `int` ou `Decimal`, jamais un `float`.
            # Les valeurs sont converties ici, explicitement.
            # / The sale service takes exact types only: converted here, explicitly.
            quantite_de_la_part = Decimal(qty_partielle)
            prix_unitaire_en_centimes = int(prix_centimes)
            argent_reel_de_la_part_en_centimes = int(amount_centimes)
            prix_achat_en_centimes = int(produit.prix_achat)

            # Vente au poids ou au volume : la ligne garde le poids dans
            # `weight_quantity`. Le coût d'achat porte sur la quantité réellement
            # servie, dans l'unité du prix d'achat (kg, L), pour la fraction de
            # l'article que paie CETTE part (sa quantité partielle : l'article au
            # poids a une quantité de 1). 350 g payés à 60 % → 0,350 × 0,6 kg.
            # / Weight/volume sale: the cost is on the real served quantity, for
            #   this part's share of the item (its partial quantity).
            vente_au_poids = bool(weight_amount) and prix_obj.poids_mesure
            if vente_au_poids:
                quantite_reellement_servie_par_la_part = (
                    Decimal(weight_amount)
                    / _diviseur_de_la_quantite_saisie(produit)
                    * quantite_de_la_part
                )
            else:
                quantite_reellement_servie_par_la_part = None

            # Le total catalogue de la part est son argent RÉEL (le débit qui la
            # paie), jamais prix × quantité partielle : la quantité partielle est
            # arrondie à 6 décimales et ne doit pas décider d'un centime.
            # Une part payée en jetons cadeau (LG) n'a rien d'offert : c'est une vente
            # ordinaire, au taux 0 (`_taux_tva_de_la_ligne_de_caisse`). L'appelant
            # écrit le règlement « jetons » (LG) de la transaction.
            # / The part's catalogue total is its REAL money, never price × partial qty.
            # A token part offers nothing: an ordinary sale at 0 % VAT.
            ligne = ajouter_article(
                vente,
                pricesold=price_sold,
                quantite=quantite_de_la_part,
                prix_unitaire=prix_unitaire_en_centimes,
                taux_tva=_taux_tva_de_la_ligne_de_caisse(
                    produit, payment_method_code
                ),
                prix_achat=prix_achat_en_centimes,
                total_catalogue_impose=argent_reel_de_la_part_en_centimes,
                quantite_pour_cout=quantite_reellement_servie_par_la_part,
                **champs_historiques_de_la_part,
            )

            toutes_les_lignes_creees.append(ligne)

            if premiere_ligne_du_groupe is None:
                premiere_ligne_du_groupe = ligne

        # ---------------------------------------------------------- #
        # Décrémentation stock : 1 SEULE FOIS sur la qty totale
        # / Stock decrement: ONCE ONLY on the total qty
        # ---------------------------------------------------------- #
        # On passe la première LigneArticle du groupe comme référence
        # pour le mouvement de stock (traçabilité).
        # / We pass the first LigneArticle of the group as reference
        # for the stock movement (traceability).
        try:
            stock_du_produit = produit.stock_inventaire
        except Stock.DoesNotExist:
            # Pas de gestion de stock pour ce produit — comportement normal
            # / No stock management for this product — normal behavior
            stock_du_produit = None

        if stock_du_produit is not None:
            if weight_amount:
                # Poids/mesure : la quantité saisie remplace contenance x qty.
                # / Weight/volume: entered quantity replaces contenance x qty.
                stock_devenu_negatif = StockService.decrementer_pour_vente(
                    stock=stock_du_produit,
                    contenance=weight_amount,
                    qty=1,
                    ligne_article=premiere_ligne_du_groupe,
                )
            else:
                # Tarif classique : contenance fixe x quantité totale
                # / Standard price: fixed contenance x total quantity
                stock_devenu_negatif = StockService.decrementer_pour_vente(
                    stock=stock_du_produit,
                    contenance=prix_obj.contenance,
                    qty=quantite,
                    ligne_article=premiere_ligne_du_groupe,
                )

            # Relire le stock depuis la DB pour avoir la quantité à jour
            # / Re-read stock from DB to get updated quantity
            stock_du_produit.refresh_from_db()

            # Si le stock vient de passer en negatif, prevenir le caissier
            # / If stock just went negative, warn the cashier
            if stock_devenu_negatif:
                produits_stock_negatif.append(
                    {
                        "name": produit.name,
                        "quantite": stock_du_produit.quantite,
                        "unite": stock_du_produit.unite,
                    }
                )

            # Données du badge : même fonction pour tous les chemins (wsocket/broadcast.py)
            # / Badge data: same function for every path
            produits_stock_mis_a_jour.append(donnees_badge_stock(stock_du_produit))

    # ------------------------------------------------------------------ #
    # Étape 3 : Chaînage HMAC (conformité LNE exigence 8)
    # / Step 3: HMAC chaining (LNE compliance req. 8)
    # ------------------------------------------------------------------ #
    config_laboutik = LaboutikConfiguration.get_solo()
    cle_hmac = config_laboutik.get_or_create_hmac_key()

    # Déterminer le sale_origin pour la chaîne HMAC
    # / Determine sale_origin for HMAC chain
    sale_origin_pour_chaine = SaleOrigin.LABOUTIK
    if toutes_les_lignes_creees:
        sale_origin_pour_chaine = toutes_les_lignes_creees[0].sale_origin

    previous_hmac_value = obtenir_previous_hmac(sale_origin=sale_origin_pour_chaine)

    for ligne_a_chainer in toutes_les_lignes_creees:
        # Part écrite par le service de vente : son HT est DÉJÀ juste (arrondi demi
        # vers le haut, HT + TVA = net). On ne le recalcule PAS : `calculer_total_ht`
        # arrondit au pair (111 c à 20 % donnerait 92 au lieu de 93). L'empreinte est
        # écrite par `.update()`, jamais par un second `save()` (qui relancerait la
        # machine à statuts de la ligne).
        # / Written by the sale service: its HT is already right, NOT recomputed.
        #   The fingerprint is written by .update(), never by a second save().
        ligne_a_chainer.previous_hmac = previous_hmac_value
        ligne_a_chainer.hmac_hash = calculer_hmac(
            ligne_a_chainer, cle_hmac, previous_hmac_value
        )
        LigneArticle.objects.filter(pk=ligne_a_chainer.pk).update(
            hmac_hash=ligne_a_chainer.hmac_hash,
            previous_hmac=ligne_a_chainer.previous_hmac,
        )

        previous_hmac_value = ligne_a_chainer.hmac_hash

    # ------------------------------------------------------------------ #
    # Étape 4 : Broadcast WebSocket des badges stock mis à jour
    # / Step 4: WebSocket broadcast of updated stock badges
    # ------------------------------------------------------------------ #
    if produits_stock_mis_a_jour:
        from django.db import transaction

        # Dédupliquer par product_uuid (même logique que _creer_lignes_articles)
        # / Deduplicate by product_uuid (same logic as _creer_lignes_articles)
        donnees_par_produit = {}
        for donnee in produits_stock_mis_a_jour:
            donnees_par_produit[donnee["product_uuid"]] = donnee
        donnees_a_broadcaster = list(donnees_par_produit.values())

        transaction.on_commit(lambda: broadcast_stock_update(donnees_a_broadcaster))

    return toutes_les_lignes_creees, produits_stock_negatif


def _creer_ou_renouveler_adhesion(
    user, product, price, contribution_value=None, first_name=None, last_name=None
):
    """
    Crée ou renouvelle une adhésion (Membership) pour un utilisateur.
    Creates or renews a membership for a user.

    LOCALISATION : laboutik/views.py

    Appelée dans le bloc atomic des fonctions de paiement pour les articles adhesion.
    Called inside the atomic block of payment functions for membership articles.

    - Si user est None (carte anonyme, pas d'email) → ne rien faire.
    - Si Membership existante pour ce (user, price) → renouveler.
    - Sinon → créer une nouvelle Membership.

    - If user is None (anonymous card, no email) → do nothing.
    - If existing Membership for this (user, price) → renew.
    - Otherwise → create a new Membership.

    L'échéance n'est PAS posée ici : l'appelant rattache l'adhésion à sa ligne de vente,
    puis appelle `_appliquer_les_effets_d_une_adhesion_vendue_en_caisse`, qui la pose
    (même code qu'en ligne). La poser aussi ici l'enregistrerait deux fois.
    / The deadline is NOT set here: the caller then calls
    `_appliquer_les_effets_d_une_adhesion_vendue_en_caisse`, which sets it (same code as
    online). Setting it here too would save it twice.

    :param user: TibilletUser ou None
    :param product: Product adhesion
    :param price: Price associé au product
    :param contribution_value: Decimal montant payé (prix libre). Si None, utilise price.prix.
    :param first_name: str prénom du membre (optionnel)
    :param last_name: str nom du membre (optionnel)
    :return: Membership ou None
    """
    if user is None:
        return None

    from django.utils import timezone as tz

    valeur_contribution = (
        contribution_value if contribution_value is not None else price.prix
    )

    # Chercher une Membership existante pour ce user + price
    # Find an existing Membership for this user + price
    membership_existante = (
        Membership.objects.filter(
            user=user,
            price=price,
        )
        .exclude(
            status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED],
        )
        .first()
    )

    if membership_existante is not None:
        # Renouveler : mettre à jour la date de contribution. L'échéance est recalculée
        # ensuite, par les effets communs d'une adhésion payée.
        # / Renew: update the contribution date. The deadline is recalculated afterwards,
        # by the shared effects of a paid membership.
        membership_existante.last_contribution = tz.now()
        membership_existante.status = Membership.LABOUTIK
        membership_existante.contribution_value = valeur_contribution
        champs_a_mettre_a_jour = ["last_contribution", "status", "contribution_value"]
        if first_name:
            membership_existante.first_name = first_name
            champs_a_mettre_a_jour.append("first_name")
        if last_name:
            membership_existante.last_name = last_name
            champs_a_mettre_a_jour.append("last_name")
        membership_existante.save(update_fields=champs_a_mettre_a_jour)
        return membership_existante

    # Créer une nouvelle Membership
    # Create a new Membership
    nouvelle_adhesion = Membership.objects.create(
        user=user,
        price=price,
        status=Membership.LABOUTIK,
        last_contribution=tz.now(),
        first_contribution=tz.now(),
        contribution_value=valeur_contribution,
        first_name=first_name or "",
        last_name=last_name or "",
    )
    return nouvelle_adhesion


def _appliquer_les_effets_d_une_adhesion_vendue_en_caisse(
    adhesion, ligne_qui_porte_l_adhesion
):
    """
    Applique à une adhésion vendue en caisse les mêmes effets qu'à une adhésion payée en
    ligne : échéance, rattachement au lieu, nom, facture par mail, newsletter, récompense.
    / Applies to a membership sold at the register the same effects as online: deadline,
    venue, name, invoice mail, newsletter, reward.

    LOCALISATION : laboutik/views.py

    Appelée DANS le bloc atomic du paiement, une fois par adhésion, APRÈS que l'adhésion
    est rattachée à sa ligne de vente. En cascade (plusieurs lignes pour une adhésion),
    on passe la ligne qui porte la clé `membership`.
    / Called INSIDE the payment atomic block, once per membership, AFTER it is linked to
    its sale line.

    FLUX :
    1. `appliquer_les_effets_d_une_adhesion_payee` (BaseBillet/triggers.py) écrit en
       base, dans la transaction : si la vente est annulée, ces écritures le sont aussi.
    2. `demander_les_taches_d_une_adhesion_payee` (BaseBillet/triggers.py) part en
       `on_commit`, APRÈS la validation en base : le worker Celery relit l'adhésion avec
       sa propre connexion, et ne la trouverait pas avant.
    Pas d'envoi à l'ancien LaBoutik : la caisse V2 ne parle pas à la caisse legacy.

    :param adhesion: Membership rendue par `_creer_ou_renouveler_adhesion`
    :param ligne_qui_porte_l_adhesion: LigneArticle rattachée à l'adhésion, ou None
    """
    from BaseBillet.triggers import (
        appliquer_les_effets_d_une_adhesion_payee,
        demander_les_taches_d_une_adhesion_payee,
    )

    # Sans ligne de vente, la récompense n'a rien à lire : aucun effet, on le signale.
    # / Without a sale line, the reward has nothing to read: no effect, report it.
    if ligne_qui_porte_l_adhesion is None:
        logger.error(
            f"Adhésion vendue en caisse {adhesion.uuid} : aucune ligne de vente ne la "
            f"porte. Aucun effet appliqué (échéance, facture, récompense)."
        )
        return

    appliquer_les_effets_d_une_adhesion_payee(adhesion)

    # Les paramètres de cette fonction sont propres à chaque appel : la fonction lambda
    # garde la bonne adhésion, même quand l'appelant boucle sur plusieurs adhésions.
    # / This function's parameters belong to each call: the lambda keeps the right
    # membership, even when the caller loops over several memberships.
    db_transaction.on_commit(
        lambda: demander_les_taches_d_une_adhesion_payee(
            adhesion, ligne_qui_porte_l_adhesion
        )
    )


def _fedow_a_deja_lie_la_carte(carte, user):
    """
    Demande a Fedow si cette carte appartient DEJA au wallet de ce membre.
    / Asks Fedow whether this card ALREADY belongs to this member's wallet.

    LOCALISATION : laboutik/views.py

    POURQUOI CE CONTROLE EXISTE : Fedow refuse `linkwallet_card_number` pour toute carte
    deja liee — y compris liee a CE membre (son serializer ne accepte que les cartes libres,
    `Card.objects.filter(user__isnull=True)`). Consequence : si Fedow traite la liaison mais
    que la reponse se perd (timeout), ou qu'une seconde caisse arrive apres, le refus
    suivant est un 400 DEFINITIF. Sans ce controle, on conclurait « Fedow refuse » et on ne
    fusionnerait jamais en local : Fedow dirait carte→membre, Lespass dirait carte anonyme,
    pour toujours. C'est exactement le bug qu'on repare.
    / Fedow rejects linkwallet_card_number for ANY already-linked card, including one linked
      to THIS member. Without this check, a lost response or a race would leave Fedow and
      Lespass permanently disagreeing.

    :param carte: CarteCashless scannee
    :param user: TibilletUser identifie (doit porter son wallet Fedow)
    :return: bool — True si Fedow rattache deja cette carte au wallet du membre.
    """
    if user.wallet is None:
        return False
    try:
        carte_chez_fedow = FedowAPI().NFCcard.card_tag_id_retrieve(carte.tag_id)
    except Exception as erreur_lecture:
        logger.warning(
            f"Verification post-echec impossible pour la carte {carte.tag_id} : "
            f"{erreur_lecture}"
        )
        return False

    if not carte_chez_fedow:
        return False
    return f"{carte_chez_fedow.get('wallet_uuid')}" == f"{user.wallet.uuid}"


def _identifier_adherent(request, articles_panier):
    """
    Identifie le membre d'une adhesion. AUCUN appel reseau, AUCUNE ecriture.
    / Identifies the membership's member. NO network call, NO write.

    LOCALISATION : laboutik/views.py

    Separee de la declaration au reseau (`_declarer_adherent_au_reseau`) parce que les deux
    ne se placent pas au meme endroit : ce controle-ci doit tomber AVANT le moindre debit,
    pour ne pas prendre l'argent d'un client qu'on refusera d'inscrire ensuite. La
    declaration, elle, doit tomber le PLUS TARD possible, juste avant la transaction : une
    fois la carte liee sur le reseau, plus rien de faillible ne doit se produire.
    / Split from the network declaration because they belong at different places: this check
      must run BEFORE any debit, so we never take money from a customer we will then refuse
      to enroll. The declaration must run as LATE as possible.

    :param request: HttpRequest (pour lire le POST)
    :param articles_panier: liste de dicts de _extraire_articles_du_panier()
    :return: tuple (user, carte) — ou None si le panier ne contient pas d'adhesion
    :raises ValueError: identification impossible ; le message est destine au caissier.
    """
    articles_adhesion = [
        a for a in articles_panier if a["product"].categorie_article == Product.ADHESION
    ]
    if not articles_adhesion:
        return None

    user_adhesion = None
    carte_client = None

    # --- Identification 1 : la carte scannee ---
    # Si la carte porte deja un membre, c'est LUI l'adherent — l'email saisi ne peut pas
    # detourner une carte deja rattachee.
    # / A card already carrying a member wins: a typed email cannot hijack it.
    tag_id_client = request.POST.get("tag_id", "").upper().strip()
    if tag_id_client:
        try:
            carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
            user_adhesion = carte_client.user
        except CarteCashless.DoesNotExist:
            logger.warning(f"Carte NFC {tag_id_client} introuvable pour adhesion")

    # --- Identification 2 : l'email saisi au comptoir ---
    # / The email typed at the counter.
    email_client = request.POST.get("email_adhesion", "").strip().lower()
    if email_client and user_adhesion is None:
        user_adhesion = get_or_create_user(email_client, send_mail=False)

    if user_adhesion is None:
        raise ValueError(_("Identification du membre obligatoire pour les adhesions"))

    return user_adhesion, carte_client


def _declarer_adherent_au_reseau(user_adhesion, carte_client, ip_du_client):
    """
    Declare le membre au reseau et lui rattache sa carte, AVANT le bloc atomic.
    / Declares the member to the network and attaches their card, BEFORE the atomic.

    LOCALISATION : laboutik/views.py

    APPELEE HORS de toute transaction, et ce n'est pas negociable. Elle fait des appels
    reseau : dans un bloc atomic, ils tiendraient un verrou DB pendant toute la latence, et
    un rollback ferait disparaitre le user local pendant que Fedow garde deja sa cle RSA —
    au retry, Fedow refuserait la nouvelle cle et cet email deviendrait indeclarable a vie.
    / Called OUTSIDE any transaction: it makes network calls. Inside an atomic they would
      hold a DB lock for the whole latency, and a rollback would drop a user whose RSA key
      Fedow already keeps — making that email undeclarable forever.

    A APPELER LE PLUS TARD POSSIBLE, juste avant la transaction : une fois la carte liee sur
    le reseau, toute sortie par exception laisserait les deux cotes en desaccord.
    / CALL AS LATE AS POSSIBLE: once the card is linked on the network, any exception would
      leave both sides disagreeing.

    :param user_adhesion: TibilletUser deja identifie par `_identifier_adherent`
    :param carte_client: CarteCashless scannee, ou None
    :param ip_du_client: str (adresse IP, pour l'audit)
    :return: dict {user, carte, fusion_locale_autorisee, avertissements}
    :raises ValueError: la vente doit etre refusee ; le message est destine au caissier.
    """
    from fedow_connect.services import declarer_wallet_user_a_fedow

    # --- Fedow est une dependance dure ---
    # Tous les lieux sont sur le reseau. Sans lui, on ne sait pas ou vit l'argent de la
    # carte : on refuse la vente plutot que de fabriquer un wallet local que Fedow ne
    # connaitra jamais.
    # / Fedow is a hard dependency. Without it we refuse the sale rather than making up a
    #   local wallet Fedow will never know.
    if not FedowConfig.get_solo().can_fedow():
        raise ValueError(_(
            "Ce lieu n'est pas connecte au reseau TiBillet : l'adhesion ne peut pas etre "
            "enregistree. Prevenez un administrateur."
        ))

    avertissements = []

    # La carte n'est a lier que si elle est encore anonyme.
    # / The card only needs linking if it is still anonymous.
    carte_a_lier = None
    if carte_client is not None and carte_client.user is None:
        carte_a_lier = carte_client

    # --- Anti-vol, en local, AVANT le reseau ---
    # Fedow ne refuse une seconde carte que si le wallet cible porte deja des jetons : un
    # membre au wallet vide passerait chez lui et serait refuse ici, et les deux cotes
    # divergeraient. On tranche donc en local, avant d'avoir rien envoye.
    # / Fedow only blocks a second card when the target wallet already holds tokens, so we
    #   decide locally before sending anything.
    if carte_a_lier is not None:
        user_a_deja_une_autre_carte = user_adhesion.cartecashless_set.exclude(
            pk=carte_a_lier.pk
        ).exists()
        if user_a_deja_une_autre_carte:
            avertissements.append(_(
                "Ce membre possede deja une carte : la carte scannee n'a pas ete rattachee. "
                "L'adhesion est bien enregistree."
            ))
            carte_a_lier = None

    # --- Declaration du membre au reseau ---
    # Seul appel qui transmet sa cle publique. Repare au passage un wallet local divergent.
    # / The only call carrying the member's public key; also repairs a diverging local wallet.
    try:
        declarer_wallet_user_a_fedow(
            user_adhesion, tenant=connection.tenant, ip=ip_du_client
        )
    except Exception as erreur_declaration:
        logger.error(
            f"Adhesion POS : declaration de {user_adhesion.email} a Fedow impossible : "
            f"{erreur_declaration}"
        )
        raise ValueError(_(
            "Le reseau TiBillet ne repond pas : l'adhesion n'a pas ete enregistree. "
            "Reessayez dans un instant."
        ))

    # --- Liaison de la carte chez Fedow ---
    # C'est Fedow qui absorbe le wallet ephemere de la carte dans celui du membre.
    # RIEN DE FAILLIBLE APRES CE POINT hors du bloc atomic : une fois la carte liee chez
    # Fedow, toute sortie par exception laisserait les deux cotes en desaccord.
    # / Fedow merges the card's ephemeral wallet into the member's. NOTHING FALLIBLE AFTER
    #   THIS POINT outside the atomic block.
    if carte_a_lier is not None:
        try:
            FedowAPI().NFCcard.linkwallet_card_number(
                user=user_adhesion, card_number=carte_a_lier.number
            )
        except Exception as erreur_liaison:
            if not _fedow_a_deja_lie_la_carte(carte_a_lier, user_adhesion):
                # REFUS METIER, pas une panne : le reseau connait deja cette carte sous un
                # autre proprietaire. On ne fusionne rien en local — sinon Lespass dirait
                # une chose et le reseau une autre — mais l'adhesion reste due, et elle n'a
                # pas besoin de portefeuille. Le solde de la carte ne bouge pas d'un centime
                # et reste recuperable par le parcours /qr/.
                # / BUSINESS REFUSAL, not an outage: the network already knows this card
                #   under another owner. Merge nothing locally, but the membership is still
                #   owed and needs no wallet. The card's balance stays untouched.
                logger.warning(
                    f"Adhesion POS : liaison de la carte {carte_a_lier.tag_id} refusee "
                    f"par le reseau : {erreur_liaison}"
                )
                avertissements.append(_(
                    "Le reseau a refuse de rattacher cette carte a ce membre. L'adhesion "
                    "est bien enregistree, et le solde de la carte est intact."
                ))
                carte_a_lier = None
            else:
                # Le reseau avait DEJA lie la carte a ce membre (reponse perdue, ou seconde
                # caisse) : le refus est un faux negatif, la fusion locale doit avoir lieu.
                # / The network had ALREADY linked it to this member: false negative.
                logger.info(
                    f"Adhesion POS : carte {carte_a_lier.tag_id} deja liee a "
                    f"{user_adhesion.email} sur le reseau, on poursuit la fusion locale."
                )

    return {
        "user": user_adhesion,
        "carte": carte_client,
        "fusion_locale_autorisee": carte_a_lier is not None,
        "avertissements": avertissements,
    }


def _resoudre_adherent_hors_atomic(request, articles_panier):
    """
    Identifie le membre PUIS le declare au reseau, en une fois, AVANT le bloc atomic.
    / Identifies the member THEN declares them to the network, in one go, BEFORE the atomic.

    LOCALISATION : laboutik/views.py

    Utilisee par les paiements especes et CB, ou rien d'irreversible ne se produit entre les
    deux etapes : on peut donc les enchainer. Le paiement NFC, lui, les appelle SEPAREMENT —
    il debite le reseau (segment legacy) entre les deux, et ce debit ne se rembourse pas.
    / Used by the cash and card flows, where nothing irreversible happens between the two
      steps. The NFC flow calls them SEPARATELY: it debits the network in between, and that
      debit cannot be refunded.

    :param request: HttpRequest (pour lire le POST)
    :param articles_panier: liste de dicts de _extraire_articles_du_panier()
    :return: dict {user, carte, fusion_locale_autorisee, avertissements} ou None
    :raises ValueError: la vente doit etre refusee ; le message est destine au caissier.
    """
    adherent_identifie = _identifier_adherent(request, articles_panier)
    if adherent_identifie is None:
        return None

    user_adhesion, carte_client = adherent_identifie
    return _declarer_adherent_au_reseau(
        user_adhesion,
        carte_client,
        request.META.get("REMOTE_ADDR", "0.0.0.0"),
    )


def _creer_adhesions_depuis_panier(
    request, articles_panier, lignes_articles=None, adherent=None
):
    """
    Cree les Memberships pour les articles adhesion du panier (CB/especes).
    Rattache chaque Membership a sa LigneArticle correspondante (FK membership).
    Creates Memberships for membership articles in the cart (card/cash).
    Links each Membership to its corresponding LigneArticle (FK membership).

    LOCALISATION : laboutik/views.py

    Appelee DANS le bloc atomic des fonctions de paiement. Elle ne fait donc AUCUN appel
    reseau : le membre a deja ete identifie et declare par
    `_resoudre_adherent_hors_atomic`, qui tourne avant la transaction.
    / Called INSIDE the atomic block, so it makes NO network call: the member was already
      identified and declared by _resoudre_adherent_hors_atomic, which runs before it.

    L'adhesion est creee MEME si la carte n'a pas pu etre rattachee : une Membership n'a
    pas besoin de portefeuille. Le caissier est prevenu par un avertissement.
    / The membership is created EVEN IF the card could not be linked: a Membership needs no
      wallet. The cashier is warned instead.

    :param request: HttpRequest (pour lire prenom/nom)
    :param articles_panier: liste de dicts retournee par _extraire_articles_du_panier()
    :param lignes_articles: liste de LigneArticle creees par _creer_lignes_articles() (pour rattacher membership)
    :param adherent: dict rendu par _resoudre_adherent_hors_atomic()
    :return: liste de Membership creees
    """
    from decimal import Decimal

    articles_adhesion = [
        a for a in articles_panier if a["product"].categorie_article == Product.ADHESION
    ]
    if not articles_adhesion:
        return []

    if adherent is None:
        # Ne peut arriver que si un appelant a oublie de resoudre le membre avant l'atomic.
        # / Only happens if a caller forgot to resolve the member before the atomic.
        raise ValueError(_("Identification du membre obligatoire pour les adhesions"))

    user_adhesion = adherent["user"]
    carte_client = adherent["carte"]

    # --- Fusion locale : la carte devient celle du membre ---
    # On passe par `CarteService.lier_a_user`, le MEME service que le parcours web `/qr/` :
    # un seul chemin de liaison dans tout le projet. Il verrouille la ligne carte
    # (`select_for_update`), est idempotent, rattrape les adhesions anonymes de la carte,
    # et delegue la fusion des Tokens a `WalletService`.
    # / Same service as the web /qr/ path: one single linking path in the whole project.
    if adherent["fusion_locale_autorisee"] and carte_client is not None:
        try:
            CarteService.lier_a_user(
                qrcode_uuid=carte_client.uuid,
                user=user_adhesion,
                ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
            )
        except (
            CarteIntrouvable,
            CarteDejaLiee,
            UserADejaCarte,
            SoldeInsuffisant,
        ) as erreur_liaison:
            # Course entre deux caisses, ou solde qui bouge sous nos pieds. On ne fusionne
            # pas, mais l'adhesion reste due : elle est creee, et le caissier est prevenu.
            # / Race between two tills, or a balance moving under our feet. No merge, but
            #   the membership is still owed: create it and warn the cashier.
            logger.warning(
                f"Adhesion POS : fusion locale de la carte {carte_client.tag_id} "
                f"impossible : {erreur_liaison}"
            )
            adherent["avertissements"].append(_(
                "La carte n'a pas pu etre rattachee au membre. L'adhesion est bien "
                "enregistree, le solde de la carte est intact."
            ))

    prenom = request.POST.get("prenom_adhesion", "").strip()
    nom = request.POST.get("nom_adhesion", "").strip()

    # Construire un index LigneArticle par product_uuid pour le rattachement
    # / Build a LigneArticle index by product_uuid for linking
    lignes_par_product = {}
    if lignes_articles:
        for ligne in lignes_articles:
            product_uuid = str(ligne.pricesold.productsold.product.uuid)
            lignes_par_product[product_uuid] = ligne

    memberships_creees = []
    for article in articles_adhesion:
        # Montant : prix libre (custom) ou prix standard
        # / Amount: free price (custom) or standard price
        custom_centimes = article.get("custom_amount_centimes")
        if custom_centimes is not None:
            contribution = Decimal(custom_centimes) / 100
        else:
            contribution = article["price"].prix

        membership = _creer_ou_renouveler_adhesion(
            user=user_adhesion,
            product=article["product"],
            price=article["price"],
            contribution_value=contribution,
            first_name=prenom,
            last_name=nom,
        )

        # Rattacher la Membership a sa LigneArticle
        # / Link the Membership to its LigneArticle
        if membership:
            memberships_creees.append(membership)
            product_uuid = str(article["product"].uuid)
            ligne_correspondante = lignes_par_product.get(product_uuid)
            if ligne_correspondante:
                ligne_correspondante.membership = membership
                ligne_correspondante.save(update_fields=["membership"])
            _appliquer_les_effets_d_une_adhesion_vendue_en_caisse(
                membership, ligne_correspondante
            )

    return memberships_creees


def imprimante_du_terminal(user):
    """
    Renvoie l'imprimante ACTIVE du terminal qui fait la demande, ou None.
    / Returns the requesting terminal's ACTIVE printer, or None.

    LOCALISATION : laboutik/views.py

    C'est LA regle de resolution de l'impression : tout ce qu'un terminal imprime
    (ticket de vente, billet, recu de rechargement, ticket X, ticket Z) sort sur SON
    imprimante — celle qui est branchee sur l'appareil, pas sur celle d'un autre.

    POURQUOI PAS LE POINT DE VENTE : en festival, une vingtaine de tablettes encaissent
    sur le meme point de vente « Bar ». Faire porter l'imprimante par le point de vente
    ferait sortir chaque ticket sur les vingt tablettes a la fois.
    Voir TECH_DOC/SESSIONS/IMPRESSION/SPEC.md.

    Renvoie None dans quatre cas, tous legitimes — aucun n'est une erreur, on n'imprime
    simplement pas :
    - l'utilisateur n'est pas authentifie (chemin Api-Key : AnonymousUser) ;
    - c'est un humain en session admin, donc pas un terminal (il n'a pas de .terminal) ;
    - le terminal n'a pas d'imprimante configurée ;
    - son imprimante est desactivee.

    :param user: l'utilisateur de la requete (request.user)
    :return: laboutik.Printer, ou None
    """
    if not user or not user.is_authenticated:
        return None

    # getattr avec une valeur par defaut FONCTIONNE sur une relation inverse OneToOne
    # absente : Django leve RelatedObjectDoesNotExist, qui herite d'AttributeError.
    # / getattr with a default DOES work on a missing reverse OneToOne relation.
    terminal = getattr(user, 'terminal', None)
    if terminal is None:
        return None

    printer = terminal.printer
    if printer is None or not printer.active:
        return None

    return printer


def imprimer_billet(ticket, reservation, event, printer):
    """
    Lance l'impression asynchrone d'un billet via Celery.
    Si aucune imprimante n'est fournie, on log sans erreur.
    / Launches asynchronous ticket printing via Celery.
    If no printer is given, logs without error.

    LOCALISATION : laboutik/views.py

    :param ticket: BaseBillet.Ticket
    :param reservation: BaseBillet.Reservation
    :param event: BaseBillet.Event
    :param printer: laboutik.Printer, resolue par imprimante_du_terminal(). Peut etre None.
    """
    if printer is None:
        logger.info(
            f"[PRINT] Pas d'imprimante active sur ce terminal — "
            f"billet {ticket.uuid} non imprime"
        )
        return

    from laboutik.printing.formatters import formatter_ticket_billet
    from laboutik.printing.tasks import imprimer_async

    ticket_data = formatter_ticket_billet(ticket, reservation, event)

    imprimer_async.delay(
        str(printer.pk),
        ticket_data,
        connection.schema_name,
    )


def _creer_billets_depuis_panier(request, articles_panier, lignes_articles=None):
    """
    Cree les Reservation + Ticket pour les articles billet du panier.
    Rattache chaque Reservation a sa LigneArticle correspondante (FK reservation).
    / Creates Reservation + Ticket for ticket articles in the cart.
    Links each Reservation to its corresponding LigneArticle (FK reservation).

    LOCALISATION : laboutik/views.py

    DOIT etre appelee a l'interieur d'un bloc transaction.atomic().
    / MUST be called inside a transaction.atomic() block.

    FLUX :
    1. Filtre les articles avec est_billet=True
    2. Identifie le client (NFC tag_id OU email)
    3. Groupe les articles par event (1 Reservation par event)
    4. Pour chaque event : verrouille (select_for_update), verifie la jauge
    5. Cree Reservation + ProductSold + PriceSold + Ticket(status=NOT_SCANNED)
    6. Rattache la LigneArticle a la Reservation
    7. Appelle imprimer_billet() → Celery async (si imprimante configurée)

    DEPENDENCIES :
    - _creer_lignes_articles() doit etre appelee AVANT (pour les LigneArticle)
    - imprimer_billet() : lance impression async via Celery si PV a une imprimante

    :param request: HttpRequest (pour lire le POST : tag_id, email, moyen_paiement)
    :param articles_panier: liste de dicts retournee par _extraire_articles_du_panier()
    :param lignes_articles: liste de LigneArticle creees par _creer_lignes_articles()
    :return: liste de Reservation creees
    :raises ValueError: si client non identifie ou jauge pleine
    """
    from BaseBillet.models import Reservation, Ticket

    # Filtrer les articles billet du panier
    # / Filter ticket articles from the cart
    articles_billet = []
    for article in articles_panier:
        if article.get("est_billet", False):
            articles_billet.append(article)

    if not articles_billet:
        return []

    # --- Identifier le client ---
    # / Identify the client
    user_billet = None

    tag_id_client = request.POST.get("tag_id", "").upper().strip()
    if tag_id_client:
        try:
            carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
            user_billet = carte_client.user
        except CarteCashless.DoesNotExist:
            logger.warning(f"Carte NFC {tag_id_client} introuvable pour billetterie")

    email_client = request.POST.get("email_adhesion", "").strip().lower()
    if email_client and user_billet is None:
        user_billet = get_or_create_user(email_client, send_mail=False)

    if user_billet is None:
        raise ValueError(_("Identification du client obligatoire pour les billets"))

    prenom = request.POST.get("prenom_adhesion", "").strip()
    nom = request.POST.get("nom_adhesion", "").strip()

    # Le code du moyen de paiement pour les tickets
    # / Payment method code for tickets
    moyen_paiement_code = request.POST.get("moyen_paiement", "")
    methode_db = MAPPING_CODES_PAIEMENT.get(moyen_paiement_code, PaymentMethod.UNKNOWN)

    # --- Grouper les articles par event (1 Reservation par event) ---
    # / Group articles by event (1 Reservation per event)
    articles_par_event = {}
    for article in articles_billet:
        event = article.get("event")
        if event is None:
            logger.warning(f"Article billet sans event : {article['price'].name}")
            continue
        event_uuid = str(event.uuid)
        if event_uuid not in articles_par_event:
            articles_par_event[event_uuid] = {
                "event": event,
                "articles": [],
            }
        articles_par_event[event_uuid]["articles"].append(article)

    # --- Construire un index LigneArticle par product_uuid pour le rattachement ---
    # / Build a LigneArticle index by product_uuid for linking
    lignes_par_product = {}
    if lignes_articles:
        for ligne in lignes_articles:
            product_uuid = str(ligne.pricesold.productsold.product.uuid)
            lignes_par_product[product_uuid] = ligne

    reservations_creees = []

    for event_uuid, groupe in articles_par_event.items():
        event = groupe["event"]
        articles_event = groupe["articles"]

        # --- Verification atomique de la jauge ---
        # Verrouiller l'event pour eviter les race conditions sur la jauge.
        # / Lock the event to prevent race conditions on the gauge.
        event_locked = Event.objects.select_for_update().get(pk=event.pk)

        places_vendues = event_locked.valid_tickets_count()
        jauge_max = event_locked.jauge_max or 0

        # Nombre total de billets demandes pour cet event
        # / Total number of tickets requested for this event
        total_billets_demandes = 0
        for article_event in articles_event:
            total_billets_demandes += article_event["quantite"]

        # Verifier la jauge globale de l'event
        # / Check the event's global gauge
        if jauge_max > 0 and places_vendues + total_billets_demandes > jauge_max:
            raise ValueError(_("Evenement %(event)s complet") % {"event": event.name})

        # Verifier la jauge par tarif (Price.stock) si definie
        # / Check per-rate gauge (Price.stock) if defined
        for article in articles_event:
            price = article["price"]
            quantite = article["quantite"]
            if price.stock is not None and price.stock > 0:
                places_vendues_prix = Ticket.objects.filter(
                    reservation__event__pk=event.pk,
                    pricesold__price__pk=price.pk,
                    status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED],
                ).count()
                if places_vendues_prix + quantite > price.stock:
                    raise ValueError(
                        _("Plus de places pour le tarif %(tarif)s")
                        % {"tarif": price.name}
                    )

        # --- Creer la Reservation ---
        # / Create the Reservation
        reservation = Reservation.objects.create(
            user_commande=user_billet,
            event=event_locked,
            status=Reservation.VALID,
            to_mail=bool(email_client),
        )
        reservations_creees.append(reservation)

        # --- Creer les Tickets (1 par unite de quantite) ---
        # / Create Tickets (1 per unit of quantity)
        for article in articles_event:
            product = article["product"]
            price = article["price"]
            quantite = article["quantite"]

            # ProductSold avec event renseigne (contrairement aux ventes classiques)
            # / ProductSold with event set (unlike standard sales)
            product_sold, _created = ProductSold.objects.get_or_create(
                product=product,
                event=event_locked,
                defaults={"categorie_article": product.categorie_article},
            )

            # PriceSold
            price_sold, _created = PriceSold.objects.get_or_create(
                productsold=product_sold,
                price=price,
                defaults={"prix": price.prix},
            )

            for _i in range(quantite):
                ticket = Ticket.objects.create(
                    reservation=reservation,
                    pricesold=price_sold,
                    status=Ticket.NOT_SCANNED,
                    first_name=prenom or user_billet.first_name or "",
                    last_name=nom or user_billet.last_name or "",
                    sale_origin=SaleOrigin.LABOUTIK,
                    payment_method=methode_db,
                )
                imprimer_billet(
                    ticket, reservation, event_locked,
                    imprimante_du_terminal(request.user),
                )

            # Rattacher la LigneArticle a la reservation
            # / Link the LigneArticle to the reservation
            product_uuid = str(product.uuid)
            ligne_correspondante = lignes_par_product.get(product_uuid)
            if ligne_correspondante:
                ligne_correspondante.reservation = reservation
                ligne_correspondante.save(update_fields=["reservation"])

    return reservations_creees


def _envoyer_billets_par_email(reservations):
    """
    Declenche l'envoi des billets par email via Celery pour chaque reservation
    qui a to_mail=True. DOIT etre appelee APRES le bloc transaction.atomic()
    pour eviter d'envoyer un email si le paiement est rollback.
    / Triggers ticket email sending via Celery for each reservation
    with to_mail=True. MUST be called AFTER the transaction.atomic() block
    to avoid sending an email if the payment is rolled back.

    LOCALISATION : laboutik/views.py

    :param reservations: liste de Reservation creees par _creer_billets_depuis_panier()
    """
    from BaseBillet.tasks import ticket_celery_mailer, webhook_reservation

    for reservation in reservations:
        # Webhook externe (notification a des systemes tiers)
        # / External webhook (notification to third-party systems)
        webhook_reservation.delay(str(reservation.pk))

        # Envoi email avec PDF billets (si email fourni)
        # Celery genere les PDF et envoie le mail.
        # / Email sending with PDF tickets (if email provided)
        # Celery generates PDFs and sends the email.
        if reservation.to_mail and reservation.user_commande.email:
            ticket_celery_mailer.delay(str(reservation.pk))


def _executer_recharges(
    articles_panier,
    wallet_client,
    carte_client,
    code_methode_paiement,
    ip_client,
    point_de_vente=None,
    vente=None,
    uuid_transaction=None,
):
    """
    Execute les recharges contenues dans le panier.
    Chaque article de recharge connait son Asset via product.asset (FK directe).
    / Executes top-ups in the cart.
    Each top-up article knows its Asset via product.asset (direct FK).

    LOCALISATION : laboutik/views.py

    DOIT etre appelee a l'interieur d'un bloc transaction.atomic().
    / MUST be called inside a transaction.atomic() block.

    :param articles_panier: liste de dicts (seulement les articles recharge)
    :param wallet_client: Wallet du client a crediter
    :param carte_client: CarteCashless du client
    :param code_methode_paiement: code du moyen de paiement ("espece", "carte_bancaire", "CH")
    :param ip_client: adresse IP de la requete
    :param point_de_vente: PointDeVente d'origine (renseigne sur les LigneArticle pour
        ventiler le CA par PV dans les rapports)
    / :param point_de_vente: Origin POS (set on LigneArticle for per-POS CA reports)
    :param vente: la `Vente` EN_ATTENTE du panier : les recharges sont des articles de
        la MEME vente que le reste du panier, hors chiffre d'affaires et TVA 0 (D10).
        Tous les chemins de la caisse passent une vente. None est transmis tel quel a
        `_creer_lignes_articles`, qui cree alors la ligne sans vente (sa branche sans
        vente, gardee pour des tests existants qui l'appellent directement).
        TODO : retirer None avec cette branche (fiche H).
    / :param vente: the cart's pending sale: top-ups are items of the SAME sale. Every
        register path passes one. None is forwarded to `_creer_lignes_articles` (its
        no-sale branch). TODO: remove None with that branch (sheet H).
    :param uuid_transaction: identifiant du paiement, pose sur les lignes de recharge
        comme sur les autres lignes du panier (le rejeu d'un double clic les retrouve)
    / :param uuid_transaction: payment id, set on the top-up lines too.
    :return: None
    """
    tenant_courant = connection.tenant
    ip_client_str = ip_client or "0.0.0.0"

    # Regrouper les articles par Asset pour faire une seule transaction par Asset
    # / Group articles by Asset to make one transaction per Asset
    articles_par_asset = {}
    for article in articles_panier:
        asset = article["product"].asset
        if asset is None:
            logger.warning(
                f"Product de recharge '{article['product'].name}' sans Asset — ignore"
            )
            continue
        if asset.uuid not in articles_par_asset:
            articles_par_asset[asset.uuid] = {
                "asset": asset,
                "articles": [],
            }
        articles_par_asset[asset.uuid]["articles"].append(article)

    for groupe in articles_par_asset.values():
        asset = groupe["asset"]
        articles_du_groupe = groupe["articles"]

        total_centimes = _calculer_total_panier_centimes(articles_du_groupe)

        # Determiner le moyen de paiement pour la LigneArticle
        # Les recharges cadeau (RC) et temps (TM) sont toujours gratuites,
        # quel que soit le moyen de paiement choisi par le caissier.
        # / Determine payment method for LigneArticle.
        # Gift (RC) and time (TM) top-ups are always free.
        methode_du_groupe = articles_du_groupe[0]["product"].methode_caisse
        est_recharge_gratuite = methode_du_groupe in METHODES_RECHARGE_GRATUITES
        code_methode_pour_ligne = (
            "gift" if est_recharge_gratuite else code_methode_paiement
        )

        TransactionService.creer_recharge(
            sender_wallet=asset.wallet_origin,
            receiver_wallet=wallet_client,
            asset=asset,
            montant_en_centimes=total_centimes,
            tenant=tenant_courant,
            ip=ip_client_str,
        )
        _creer_lignes_articles(
            articles_du_groupe,
            code_methode_pour_ligne,
            asset_uuid=asset.uuid,
            carte=carte_client,
            wallet=wallet_client,
            uuid_transaction=uuid_transaction,
            point_de_vente=point_de_vente,
            vente=vente,
        )


def _ouvrir_la_vente_de_caisse(
    request,
    point_de_vente,
    uuid_transaction,
    consigne_dans_panier,
    carte_client,
    adherent,
):
    """
    Ouvre la vente d'un encaissement à UN moyen de paiement (espèces, CB, chèque,
    OFFRIR). Appelée DANS le `transaction.atomic()` du paiement, avant les lignes.
    / Opens the sale of a one-method collection, inside the payment's atomic block.

    LOCALISATION : laboutik/views.py

    - nature : AVOIR pour un retour de consigne (le panier n'a alors que des retours :
      garde de `_executer_paiement`), VENTE sinon, recharges comprises (une recharge est
      un article hors chiffre d'affaires d'une vente ordinaire, D10) ;
    - clé d'idempotence : l'identifiant du paiement (`uuid_transaction`), le même que
      sur les lignes. Un rejeu de la même clé retrouve cette vente ;
    - client : l'adhérent identifié, sinon le titulaire de la carte du client ;
    - carte : la carte du client (recharges), si elle est connue.
    / AVOIR for a deposit return, VENTE otherwise; the payment id is the idempotency key.

    FLUX : _payer_par_carte_ou_cheque / _payer_en_especes → CETTE FONCTION →
    _creer_lignes_articles(vente=...) → _executer_recharges(vente=...) →
    _regler_et_encaisser_la_vente_de_caisse()

    :return: la `Vente` EN_ATTENTE
    """
    if consigne_dans_panier:
        nature_de_la_vente = Vente.Nature.AVOIR
    else:
        nature_de_la_vente = Vente.Nature.VENTE

    client_de_la_vente = None
    if adherent is not None:
        client_de_la_vente = adherent["user"]
    elif carte_client is not None:
        client_de_la_vente = carte_client.user

    tag_id_carte_manager = request.POST.get("tag_id_cm", "")
    return ouvrir_vente(
        origine=SaleOrigin.LABOUTIK,
        nature=nature_de_la_vente,
        point_de_vente=point_de_vente,
        operateur=_operateur_de_la_caisse(request, tag_id_carte_manager),
        client=client_de_la_vente,
        carte=carte_client,
        idempotency_key=str(uuid_transaction),
    )


def _regler_et_encaisser_la_vente_de_caisse(vente, articles_panier, moyen_paiement_code):
    """
    Écrit le règlement d'un encaissement à UN moyen de paiement, puis encaisse la vente.
    Dernière étape du `transaction.atomic()` du paiement.
    / Writes the payment of a one-method collection, then settles the sale. Last step.

    LOCALISATION : laboutik/views.py

    - espèces, CB, chèque : UN règlement, du montant encaissé (la somme demandée au
      client, sans les recharges cadeau ; négatif pour un retour de consigne) ;
    - OFFRIR (code « gift ») : aucun règlement ici. Le service de vente a déjà écrit un
      règlement « offert » (FREE) par article offert à montant non nul ;
    - aucun règlement de 0 : une vente gratuite n'en a pas.
    Puis `encaisser_vente` vérifie les deux égalités de la vente et pose son numéro :
    si elles ne tiennent pas, il lève `EgaliteDeVenteRompue` et toute la transaction du
    paiement est annulée (lignes, recharges, adhésions).
    / Cash, card, cheque: one payment of the collected amount; GIFT: none here (the
    service wrote FREE). Then settle: a broken equality rolls back the whole payment.

    :param vente: la `Vente` EN_ATTENTE ouverte par `_ouvrir_la_vente_de_caisse`
    :param articles_panier: liste de dicts de _extraire_articles_du_panier()
    :param moyen_paiement_code: code d'interface ("espece", "carte_bancaire", "CH", "gift")
    :return: la `Vente` encaissée
    """
    moyen_en_base = MAPPING_CODES_PAIEMENT[moyen_paiement_code]
    paiement_offert_par_le_lieu = moyen_en_base == PaymentMethod.FREE

    if not paiement_offert_par_le_lieu:
        montant_encaisse_en_centimes = _somme_encaissee_du_panier_en_centimes(
            articles_panier
        )
        if montant_encaisse_en_centimes != 0:
            ajouter_reglement(
                vente,
                moyen=moyen_en_base,
                montant=montant_encaisse_en_centimes,
            )

    return encaisser_vente(vente)


# -------------------------------------------------------------------------- #
#  ViderCarteSerializer — validation du POST /laboutik/paiement/vider_carte/  #
#  / ViderCarteSerializer — validation for POST /laboutik/paiement/vider_carte/ #
# -------------------------------------------------------------------------- #


class ViderCarteSerializer(serializers.Serializer):
    """
    Valide le POST de saisie d'un vider carte au POS.
    Validates the POST form for a POS card refund.
    """

    tag_id = serializers.CharField(max_length=8)
    tag_id_cm = serializers.CharField(max_length=8)
    uuid_pv = serializers.UUIDField()
    vider_carte = serializers.BooleanField(required=False, default=False)

    def validate_tag_id(self, value):
        return value.strip().upper()

    def validate_tag_id_cm(self, value):
        return value.strip().upper()


# --------------------------------------------------------------------------- #
#  PaiementViewSet — HTMX partials du flux de paiement                        #
# --------------------------------------------------------------------------- #


class PaiementViewSet(viewsets.ViewSet):
    """
    Partials HTMX pour le flux de paiement de la caisse.
    HTMX partials for the cash register payment flow.

    Flux de paiement (3 étapes) / Payment flow (3 steps) :
    1. moyens_paiement() → affiche les boutons de paiement disponibles / shows available payment buttons
    2. confirmer()       → écran de confirmation + saisie espèce / confirmation screen + cash input
    3. payer()           → exécute le paiement (DB) + retour succès ou fonds insuffisants
                           executes payment (DB) + returns success or insufficient funds

    Annexes / Utilities :
    - lire_nfc()       → attente lecture carte NFC pour paiement cashless / NFC card read for cashless payment
    - verifier_carte() → attente lecture carte NFC pour vérification solde / NFC card read for balance check
    - retour_carte()   → affiche le solde de la carte scannée / shows the scanned card balance
    """

    permission_classes = [HasLaBoutikTerminalAccess]

    # ----------------------------------------------------------------------- #
    #  Garde stock au clic : texte du refus                                    #
    #  Click stock guard: refusal message                                      #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["get"],
        url_path="stock_insuffisant",
        url_name="stock_insuffisant",
    )
    def stock_insuffisant(self, request):
        """
        GET /laboutik/paiement/stock_insuffisant/
        Rend la popup standard (hx_messages.html) qui explique un ajout refuse.
        / Renders the standard popup explaining a refused cart addition.

        LOCALISATION : laboutik/views.py

        FLUX :
        1. Clic sur une tuile (ou un tarif de la popup).
        2. articles.js:verifierStockAvantAjout() refuse l'ajout tout de suite
           (pas d'attente reseau pour bloquer).
        3. Elle appelle cette vue en htmx.ajax → cible #messages (outerHTML).
        4. On relit le stock EN BASE et on ecrit un message clair :
           deja dans le panier / en stock / encore possible.

        Si le stock en base permet finalement l'ajout (le badge de la tuile
        etait en retard), on le dit : le caissier retouche l'article.
        / If the DB stock actually allows it (stale tile badge), say so.

        Parametres GET (StockInsuffisantSerializer) :
        - product_uuid, quantite_au_panier, quantite_a_ajouter
        """
        from laboutik.serializers import StockInsuffisantSerializer

        serializer = StockInsuffisantSerializer(data=request.GET)
        if not serializer.is_valid():
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Stock insuffisant — vente refusée."),
                },
                status=400,
            )

        produit = get_object_or_404(
            Product, uuid=serializer.validated_data["product_uuid"]
        )
        try:
            stock = produit.stock_inventaire
        except Stock.DoesNotExist:
            stock = None

        # Pas de stock gere, ou vente hors stock autorisee : l'ajout etait permis.
        # Le badge de la tuile etait en retard sur la base.
        # / No managed stock, or out-of-stock sale allowed: the tile badge was stale.
        if stock is None or stock.autoriser_vente_hors_stock:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "info",
                    "msg_content": _(
                        "Le stock vient de changer. Touchez à nouveau l'article."
                    ),
                },
            )

        quantite_au_panier = serializer.validated_data["quantite_au_panier"]
        quantite_a_ajouter = serializer.validated_data["quantite_a_ajouter"]
        encore_possible = max(stock.quantite - quantite_au_panier, 0)

        if encore_possible >= quantite_a_ajouter:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "info",
                    "msg_content": _(
                        "Le stock vient de changer. Touchez à nouveau l'article."
                    ),
                },
            )

        # Message en lignes courtes (FALC). Quantites lisibles : 2, 50 cl, 1.5 L, 800 g.
        # / Short lines. Readable quantities.
        lignes_du_message = [
            _("%(nom)s : stock insuffisant.") % {"nom": produit.name},
            _("Déjà dans le panier : %(quantite)s")
            % {"quantite": _formater_stock_lisible(quantite_au_panier, stock.unite)},
            _("En stock : %(quantite)s")
            % {"quantite": _formater_stock_lisible(stock.quantite, stock.unite)},
        ]
        if encore_possible > 0:
            lignes_du_message.append(
                _("Vous pouvez encore en ajouter : %(quantite)s")
                % {"quantite": _formater_stock_lisible(encore_possible, stock.unite)}
            )
        else:
            lignes_du_message.append(_("Vous ne pouvez plus en ajouter."))

        return render(
            request,
            "laboutik/partial/hx_messages.html",
            {
                "msg_type": "warning",
                "msg_content": "\n".join(str(ligne) for ligne in lignes_du_message),
            },
        )

    # ----------------------------------------------------------------------- #
    #  Étape 1 : afficher les moyens de paiement disponibles                   #
    #  Step 1: show available payment methods                                  #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["post"],
        url_path="moyens_paiement",
        url_name="moyens_paiement",
    )
    def moyens_paiement(self, request):
        """
        POST /laboutik/paiement/moyens_paiement/
        Reçoit les articles sélectionnés (via le formulaire d'addition),
        calcule le total et retourne les boutons de paiement disponibles.
        Receives selected articles (from the addition form),
        calculates the total and returns available payment buttons.
        """
        # --- Charger le PV depuis la DB ---
        # --- Load PV from DB ---
        uuid_pv = request.POST.get("uuid_pv")
        try:
            point_de_vente = PointDeVente.objects.get(uuid=uuid_pv)
        except (PointDeVente.DoesNotExist, ValueError):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Point de vente introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=404
            )

        # --- Vérifier que la carte primaire a accès au PV ---
        # --- Check that the primary card has access to the PV ---
        tag_id_carte_manager = request.POST.get("tag_id_cm", "")
        _valider_carte_primaire_pour_pv(tag_id_carte_manager, uuid_pv)

        state = _construire_state(point_de_vente, user=request.user)

        # --- Extraire les articles du panier depuis le POST ---
        # --- Extract cart articles from POST ---
        try:
            articles_panier = _extraire_articles_du_panier(request.POST, point_de_vente)
        except ValueError as e:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": str(e),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # --- Une seule monnaie par panier : refus des le clic sur VALIDER ---
        # La garde reelle est dans _executer_paiement ; ici, le caissier est
        # prevenu avant de choisir un moyen de paiement.
        # / One currency per cart: the cashier is told as soon as they validate.
        try:
            _monnaie_du_panier(articles_panier)
        except ValueError as erreur_de_monnaie:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": str(erreur_de_monnaie),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # --- Vérifier le stock AVANT de proposer les moyens de paiement ---
        # Sans ce contrôle, le caissier choisissait espèces ou CB,
        # et l'erreur "stock insuffisant" n'arrivait qu'au moment de payer.
        # Le contrôle reste aussi dans payer() : un autre poste a pu vendre
        # le dernier article entre les deux clics.
        # Les recharges ne sont pas concernées (même filtre que dans payer()).
        # / Check stock BEFORE showing payment methods, so the error shows on VALIDER
        # instead of after the payment method choice. payer() keeps its own check.
        articles_hors_recharges = []
        for article_du_panier in articles_panier:
            if article_du_panier["product"].methode_caisse not in METHODES_RECHARGE:
                articles_hors_recharges.append(article_du_panier)
        erreurs_stock = _valider_stock_panier(articles_hors_recharges)
        if erreurs_stock:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _formater_erreurs_stock(erreurs_stock),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # --- Calculer le total en centimes puis convertir en euros ---
        # --- Calculate total in centimes then convert to euros ---
        total_centimes = _calculer_total_panier_centimes(articles_panier)
        total_en_euros = total_centimes / 100

        # --- Déterminer les moyens de paiement disponibles ---
        # --- Determine available payment methods ---
        # Si le panier contient des recharges (RE/RC/TM), NFC est exclu
        # If the cart contains top-ups (RE/RC/TM), NFC is excluded
        moyens_paiement_disponibles = _determiner_moyens_paiement(
            point_de_vente, articles_panier
        )

        # Si le panier contient des recharges, le template doit demander un scan NFC client
        # If the cart contains top-ups, the template must request a client NFC scan
        panier_a_recharges = _panier_contient_recharges(articles_panier)

        # Si le panier contient des adhésions, le template doit demander l'identification client
        # (scan NFC ou formulaire email/nom/prénom)
        # If the cart contains memberships, the template must request client identification
        # (NFC scan or email/name form)
        panier_a_adhesions = any(
            a["product"].categorie_article == Product.ADHESION for a in articles_panier
        )

        # Si le panier contient des billets, on demande aussi l'identification
        # (pour Reservation.user_commande). L'email est optionnel (to_mail).
        # / If the cart contains tickets, we also request identification
        # (for Reservation.user_commande). Email is optional (to_mail).
        panier_a_billets = False
        for article_panier in articles_panier:
            if article_panier.get("est_billet", False):
                panier_a_billets = True
                break

        # Le panier necessite un client si il contient des recharges, adhesions ou billets.
        # Dans ce cas, on demande une identification AVANT le choix du moyen de paiement.
        # / Cart requires a client if it contains top-ups, memberships or tickets.
        # In that case, we ask for identification BEFORE payment method choice.
        panier_necessite_client = (
            panier_a_recharges or panier_a_adhesions or panier_a_billets
        )

        # Liste des moyens de paiement en CSV pour propagation via templates HTMX
        # / Payment methods as CSV for propagation through HTMX templates
        moyens_paiement_csv = ",".join(moyens_paiement_disponibles)

        # Tuile OFFRIR : carte primaire en mode gerant et panier offrable.
        # / GIFT tile: manager-mode primary card and giftable cart.
        est_mode_gerant = _panier_peut_etre_offert(articles_panier, tag_id_carte_manager)

        # Le flux de remboursement ne s'affiche que si le panier est ENTIEREMENT
        # composé de retours. Sur un panier mélangé, le total passé en valeur absolue
        # annoncerait « à rembourser » un montant que le client doit : le caissier
        # lirait l'inverse de la vérité. Le POST d'un tel panier est refusé par
        # `payer()`, mais cet écran vient avant.
        # / The refund screen only shows on a cart made ONLY of returns: on a mixed cart
        #   the absolute total would announce a refund for money the customer owes.
        consigne_dans_panier = _panier_est_uniquement_retour_consigne(articles_panier)
        if consigne_dans_panier:
            total_en_euros = abs(total_en_euros)

        context = {
            "state": state,
            "moyens_paiement": moyens_paiement_disponibles,
            "moyens_paiement_csv": moyens_paiement_csv,
            # Total en euros, ou dans la monnaie d'un panier en points
            # / Total in euros, or in a points cart's currency
            "currency_data": _currency_data_du_panier(articles_panier),
            "total": total_en_euros,
            "mode_gerant": est_mode_gerant,
            "deposit_is_present": consigne_dans_panier,
            "comportement": point_de_vente.comportement,
            "panier_a_recharges": panier_a_recharges,
            "panier_a_adhesions": panier_a_adhesions,
            "panier_a_billets": panier_a_billets,
            "panier_necessite_client": panier_necessite_client,
            # Nouvelle cle a chaque affichage des moyens de paiement : un double
            # envoi de payer() arrive avec la meme cle (_executer_avec_cle_idempotence).
            # / New key each time payment methods are shown.
            "cle_idempotence_paiement": uuid_module.uuid4(),
        }
        return render(request, "laboutik/partial/hx_display_type_payment.html", context)

    # ----------------------------------------------------------------------- #
    #  Étape 2 : écran de confirmation avant paiement                          #
    #  Step 2: confirmation screen before payment                              #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["get"], url_path="confirmer", url_name="confirmer")
    def confirmer(self, request):
        """
        GET /laboutik/paiement/confirmer/
        Affiche l'écran de confirmation avec le moyen de paiement choisi.
        Pour les espèces, un champ de saisie permet d'entrer la somme donnée.
        Displays the confirmation screen with the chosen payment method.
        For cash, an input field allows entering the amount given.
        """
        moyen_paiement_choisi = request.GET.get("method")
        uuid_transaction = request.GET.get("uuid_transaction", "")

        # Convertir le total en float — le parametre GET peut contenir une virgule
        # (locale francaise : USE_L10N rend "5,0" au lieu de "5.0" dans le template).
        # / Convert total to float — GET param may contain comma (French locale).
        total_brut = request.GET.get("total", "0")
        total_brut = total_brut.replace(",", ".")
        try:
            total_a_payer = float(total_brut)
        except (ValueError, TypeError):
            total_a_payer = 0

        # complement=1 : on vient de la popup « Complément de paiement »
        # (hx_complement_paiement.html). Valider soumettra #complement-form
        # vers payer_complementaire, et pas #addition-form vers payer.
        # / complement=1: coming from the NFC complement popup. Validate will
        # submit #complement-form to payer_complementaire instead of payer.
        est_complement = request.GET.get("complement") == "1"

        # recharge=1 : on vient de l'ecran « Recharger » du check carte
        # (hx_card_recharge.html). Valider soumettra #card-recharge-form
        # vers payer, et pas #addition-form.
        # / recharge=1: coming from the check-card top-up screen. Validate will
        # submit #card-recharge-form to payer instead of #addition-form.
        est_recharge = request.GET.get("recharge") == "1"

        context = {
            "method": moyen_paiement_choisi,
            "total": total_a_payer,
            "payment_translation": PAYMENT_METHOD_TRANSLATIONS.get(
                moyen_paiement_choisi, ""
            ),
            "uuid_transaction": uuid_transaction,
            "currency_data": CURRENCY_DATA,
            "est_complement": est_complement,
            "est_recharge": est_recharge,
        }
        return render(request, "laboutik/partial/hx_confirm_payment.html", context)

    # ----------------------------------------------------------------------- #
    #  Étape 3 : exécuter le paiement                                          #
    #  Step 3: execute the payment                                             #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["post"], url_path="payer", url_name="payer")
    def payer(self, request):
        """
        POST /laboutik/paiement/payer/
        Protege le paiement contre un double envoi, puis l'execute.
        / Guards the payment against a double submit, then runs it.

        LOCALISATION : laboutik/views.py

        Le serveur a pose une cle d'idempotence dans le formulaire au moment
        d'afficher les moyens de paiement (moyens_paiement, champ
        cle_idempotence_paiement). Un double appui sur « Valider », ou un
        renvoi apres une coupure reseau, arrive donc avec la MEME cle.
        Voir _executer_avec_cle_idempotence().
        / The server put an idempotency key in the form when showing the payment
        methods. A double tap or a network retry arrives with the SAME key.

        Sans cle (ancien client) : le paiement s'execute comme avant.
        / Without a key (old client): the payment runs as before.
        """
        return _executer_avec_cle_idempotence(
            request,
            self._executer_paiement,
        )

    def _executer_paiement(self, request, uuid_transaction_impose=None):
        """
        Exécute le paiement et crée les LigneArticle en base.
        Executes the payment and creates LigneArticle records in DB.

        Le formulaire d'addition (côté client) envoie :
        The addition form (client-side) sends:
        - moyen_paiement : code du moyen ("espece", "carte_bancaire", "CH", "nfc")
        - total : montant en centimes / amount in cents
        - given_sum : somme donnée en centimes (espèces uniquement) / given sum in cents (cash only)
        - tag_id : tag NFC du client (cashless uniquement) / client NFC tag (cashless only)
        - uuid_pv : UUID du point de vente / point of sale UUID
        - uuid_transaction : UUID transaction précédente (complément fonds insuffisants)
                             previous transaction UUID (insufficient funds top-up)
        - repid-<uuid> : quantité de chaque article / quantity of each article
        """
        # --- Charger le PV depuis la DB ---
        # --- Load PV from DB ---
        donnees_paiement = request.POST.dict()
        uuid_pv = donnees_paiement.get("uuid_pv")
        try:
            point_de_vente = PointDeVente.objects.get(uuid=uuid_pv)
        except (PointDeVente.DoesNotExist, ValueError):
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": _("Point de vente introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=404
            )

        # --- Vérifier que la carte primaire a accès au PV ---
        # --- Check that the primary card has access to the PV ---
        tag_id_carte_manager = donnees_paiement.get("tag_id_cm", "")
        _valider_carte_primaire_pour_pv(tag_id_carte_manager, uuid_pv)

        state = _construire_state(point_de_vente, user=request.user)

        # --- Normaliser les montants (les champs texte du formulaire → entiers) ---
        # --- Normalize amounts (form text fields → integers) ---
        donnees_paiement["total"] = int(donnees_paiement.get("total", 0))
        somme_donnee_brute = donnees_paiement.get("given_sum", "")
        if somme_donnee_brute == "":
            donnees_paiement["given_sum"] = 0
        else:
            # Le JS envoie « somme en euros x 100 ». Ce calcul peut donner
            # un nombre a virgule (ex : 329.99999999999994). int() planterait :
            # on arrondit d'abord, comme dans payer_complementaire.
            # / The JS sends "euros x 100", which can be a float: round first.
            try:
                donnees_paiement["given_sum"] = int(round(float(somme_donnee_brute)))
            except (ValueError, TypeError):
                donnees_paiement["given_sum"] = 0
        donnees_paiement["missing"] = 0

        # --- Extraire les articles du panier depuis la DB ---
        # --- Extract cart articles from DB ---
        try:
            articles_panier = _extraire_articles_du_panier(request.POST, point_de_vente)
        except ValueError as e:
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": str(e),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # --- Une recharge cadeau se fait à part ---
        # La caisse additionne tous les articles pour la somme à payer : mêlée à
        # d'autres articles, la recharge cadeau serait payée par le client. Refus AVANT
        # l'aiguillage, donc avant toute écriture et tout débit de carte. Seule, elle
        # est créditée sans paiement (`identifier_client`).
        # / A gift top-up is done on its own: mixed carts refused before any write.
        if _panier_melange_recharge_cadeau_et_autres_articles(articles_panier):
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": _(
                    "La recharge cadeau se fait à part : retirez les autres articles."
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # --- Calculer le total en centimes ---
        # --- Calculate total in centimes ---
        consigne_dans_panier = _panier_contient_retour_consigne(articles_panier)
        total_centimes = _calculer_total_panier_centimes(articles_panier)
        total_en_euros = total_centimes / 100
        if consigne_dans_panier:
            total_en_euros = abs(total_en_euros)
            total_centimes = abs(total_centimes)

        moyen_paiement_code = donnees_paiement.get("moyen_paiement", "")

        # --- Les deux gardes de la monnaie du panier ---
        # Elles tombent AVANT l'aiguillage, donc avant toute écriture en base.
        # `payer()` ne confronte jamais le moyen reçu à la liste proposée : sans
        # ces gardes, un POST forgé « espece » passerait par _creer_lignes_articles(),
        # qui ne lit pas la monnaie du tarif et ne débite aucune carte. La vente de
        # 300 points serait enregistrée comme 300 € en espèces.
        # / The two cart-currency guards, before any routing and any DB write.
        #   A forged cash POST would otherwise record 300 points as 300 € cash.
        # 1. Une seule monnaie par panier. / One currency per cart.
        try:
            monnaie_du_panier = _monnaie_du_panier(articles_panier)
        except ValueError as erreur_de_monnaie:
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": str(erreur_de_monnaie),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # 2. Un panier en points ou en temps se paie uniquement par carte NFC.
        # / A points or time cart is paid only by NFC card.
        panier_en_points = monnaie_du_panier is not None
        if panier_en_points and moyen_paiement_code != "nfc":
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": _(
                    "Un panier en points ou en temps se paie uniquement avec la "
                    "carte du client."
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # --- Les deux gardes du retour de consigne ---
        # Elles tombent AVANT l'aiguillage, donc avant toute écriture en base.
        # / The two deposit-return guards, before any routing and any DB write.

        if consigne_dans_panier:
            # 1. Le panier mélangé est refusé.
            # Le total ci-dessus vient d'être passé en valeur absolue. Sur un panier
            # mixte (une bière à 3 € et un retour à -1 €), il vaut 2 € et l'écran
            # annoncerait « à rembourser 2 € » alors que le client DOIT 2 €. Un retour
            # de consigne est une opération isolée, comme au comptoir.
            # / Mixed carts refused: abs() above only makes sense on a wholly negative
            #   cart, otherwise the screen tells the cashier the opposite of the truth.
            if not _panier_est_uniquement_retour_consigne(articles_panier):
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _(
                        "Un retour de consigne se règle seul, sans autre article "
                        "dans le panier."
                    ),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request,
                    "laboutik/partial/hx_messages.html",
                    context_erreur,
                    status=400,
                )

            # 2. On ne rembourse qu'en espèces ou sur la carte du client.
            # Le filtrage des boutons est un confort d'affichage : `payer()` ne
            # confronte jamais le moyen reçu à la liste proposée, donc un POST forgé
            # passerait outre sans cette garde.
            # / Cash or the customer's card only. Button filtering is cosmetic: payer()
            #   never checks the posted method against the offered list.
            if moyen_paiement_code in ("carte_bancaire", "CH"):
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _(
                        "Un retour de consigne se rembourse en espèces ou sur la "
                        "carte du client."
                    ),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request,
                    "laboutik/partial/hx_messages.html",
                    context_erreur,
                    status=400,
                )

            # 3. Sur la carte du client, rendre de l'argent est une RECHARGE.
            # La cascade de débit de `_payer_par_nfc` cherche de quoi prélever : sur un
            # montant négatif elle s'arrête sans rien écrire, tout en affichant un
            # succès. Le remboursement a donc son propre flux.
            # / On the customer's card, giving money back is a TOP-UP. The debit cascade
            #   would stop without writing anything on a negative amount.
            if moyen_paiement_code == "nfc":
                return self._rembourser_consigne_par_nfc(
                    request,
                    state,
                    donnees_paiement,
                    articles_panier,
                    total_en_euros,
                    point_de_vente,
                    uuid_transaction_impose=uuid_transaction_impose,
                )

        # --- Transaction précédente (complément après fonds insuffisants) ---
        # --- Previous transaction (top-up after insufficient funds) ---
        # Phase 3 : sera implémenté avec fedow_core
        # Phase 3: will be implemented with fedow_core
        transaction_precedente = None

        # --- Aiguillage vers le bon flux de paiement ---
        # --- Route to the correct payment flow ---
        # `moyen_paiement_code` a été lu plus haut, avec les gardes du retour de consigne.
        # / Already read above, alongside the deposit-return guards.
        logger.info(
            f"payer: moyen={moyen_paiement_code}, total={total_centimes}cts, articles={len(articles_panier)}"
        )

        if moyen_paiement_code in ("carte_bancaire", "CH"):
            return self._payer_par_carte_ou_cheque(
                request,
                state,
                donnees_paiement,
                articles_panier,
                total_en_euros,
                total_centimes,
                consigne_dans_panier,
                transaction_precedente,
                moyen_paiement_code,
                uuid_transaction_impose=uuid_transaction_impose,
            )

        if moyen_paiement_code == "espece":
            return self._payer_en_especes(
                request,
                state,
                donnees_paiement,
                articles_panier,
                total_en_euros,
                total_centimes,
                consigne_dans_panier,
                transaction_precedente,
                moyen_paiement_code,
                uuid_transaction_impose=uuid_transaction_impose,
            )

        if moyen_paiement_code == "nfc":
            return self._payer_par_nfc(
                request,
                state,
                donnees_paiement,
                articles_panier,
                total_en_euros,
                total_centimes,
                consigne_dans_panier,
                moyen_paiement_code,
                point_de_vente,
                uuid_transaction_impose=uuid_transaction_impose,
            )

        # --- Panier offert : gratuit (billet a 0 €) ou OFFRIR du gerant ---
        # Le bouton « Valider » d'un panier gratuit et la tuile OFFRIR envoient
        # moyen_paiement=gift : la vente est enregistree « Offert » (FREE).
        # Le serveur decide seul : le total recalcule vaut 0, ou la carte primaire
        # est en mode gerant (lu en base) et le panier est offrable. Sans cette
        # garde, un POST force offrirait n'importe quel panier.
        # / Gifted cart: free (0 € ticket) or the manager's GIFT. The server alone
        #   decides: recomputed total is 0, or manager mode (from the database).
        if moyen_paiement_code == "gift":
            panier_est_gratuit = total_centimes == 0 and len(articles_panier) > 0
            panier_offert_par_le_gerant = _panier_peut_etre_offert(
                articles_panier, donnees_paiement.get("tag_id_cm", "")
            )
            if not panier_est_gratuit and not panier_offert_par_le_gerant:
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _("Ce panier n'est pas gratuit."),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request,
                    "laboutik/partial/hx_messages.html",
                    context_erreur,
                    status=400,
                )

            # Meme traitement qu'une CB : lignes de vente, billets, adhesions.
            # Le code "gift" donne PaymentMethod.FREE (MAPPING_CODES_PAIEMENT).
            # / Same processing as a card payment; "gift" maps to PaymentMethod.FREE.
            return self._payer_par_carte_ou_cheque(
                request,
                state,
                donnees_paiement,
                articles_panier,
                total_en_euros,
                total_centimes,
                consigne_dans_panier,
                transaction_precedente,
                moyen_paiement_code,
                uuid_transaction_impose=uuid_transaction_impose,
            )

        # Moyen de paiement non reconnu → erreur
        # Unrecognized payment method → error
        context_erreur = {
            "action": "initUrlAddition();",
            "msg_type": "warning",
            "msg_content": _("Il y a une erreur !"),
            "selector_bt_retour": "#messages",
        }
        return render(
            request, "laboutik/partial/hx_messages.html", context_erreur, status=400
        )

    # ------------------------------------------------------------------ #
    #  Flux de paiement : carte bancaire ou chèque                        #
    #  Payment flow: credit card or check                                 #
    # ------------------------------------------------------------------ #

    def _payer_par_carte_ou_cheque(
        self,
        request,
        state,
        donnees_paiement,
        articles_panier,
        total_en_euros,
        total_centimes,
        consigne_dans_panier,
        transaction_precedente,
        moyen_paiement_code,
        uuid_transaction_impose=None,
    ):
        """
        Paiement par carte bancaire ("carte_bancaire") ou chèque ("CH").
        Credit card or check payment.

        LOCALISATION : laboutik/views.py

        Pas de vérification côté serveur (le TPE ou le chèque est géré en dehors).
        On crée les LigneArticle en base puis on affiche le succès.
        Si le panier contient des recharges (RE/RC/TM), on crédite le wallet client.
        No server-side verification (the card terminal or check is handled externally).
        We create LigneArticle records in DB then display success.
        If the cart contains top-ups (RE/RC/TM), we credit the client wallet.
        """
        ip_client = request.META.get("REMOTE_ADDR", "0.0.0.0")

        # Recuperer le PV depuis les donnees de paiement (pour l'impression)
        # / Get the POS from payment data (for printing)
        uuid_pv = donnees_paiement.get("uuid_pv", "")
        point_de_vente = PointDeVente.objects.get(
            uuid=uuid_pv
        )

        # Identifiant unique de ce paiement — regroupe toutes les LigneArticle.
        # Si payer() a recu une cle d'idempotence, on la reutilise :
        # c'est elle qui permet de detecter un double envoi.
        # / Unique ID for this payment — groups all LigneArticle records.
        # Reuses the idempotency key from payer() when there is one.
        uuid_transaction = uuid_transaction_impose or uuid_module.uuid4()

        # Séparer articles normaux et recharges
        # Separate normal articles and top-ups
        articles_normaux = [
            a
            for a in articles_panier
            if a["product"].methode_caisse not in METHODES_RECHARGE
        ]
        articles_recharge = [
            a
            for a in articles_panier
            if a["product"].methode_caisse in METHODES_RECHARGE
        ]
        reservations_billets = []

        # Validation amont du stock pour les articles normaux.
        # Si un article a autoriser_vente_hors_stock=False et que le stock est
        # insuffisant, on bloque la vente AVANT d'ouvrir transaction.atomic().
        # / Upstream stock validation for normal articles.
        # If an article has autoriser_vente_hors_stock=False and stock is insufficient,
        # block the sale BEFORE opening transaction.atomic().
        erreurs_stock = _valider_stock_panier(articles_normaux)
        if erreurs_stock:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _formater_erreurs_stock(erreurs_stock),
                },
                status=400,
            )

        # Resolution du wallet client AVANT le bloc atomic : _obtenir_ou_creer_wallet
        # peut faire un appel reseau Fedow (latence). Le faire DANS l'atomic
        # tiendrait un verrou DB pendant toute la latence reseau.
        # / Resolve the client wallet BEFORE the atomic block: _obtenir_ou_creer_wallet
        # may do a Fedow network call (latency). Doing it INSIDE the atomic would
        # hold a DB lock for the whole network latency.
        carte_client = None
        wallet_client = None
        if articles_recharge:
            tag_id_client = request.POST.get("tag_id", "").upper().strip()
            if not tag_id_client:
                raise ValueError(_("Tag NFC client requis pour les recharges"))

            carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
            wallet_client = _obtenir_ou_creer_wallet(carte_client)

        # Resolution du membre d'une adhesion AVANT le bloc atomic, pour la meme raison de
        # latence — et une de plus, qui pese lourd : cette resolution DECLARE le membre a
        # Fedow. Faite dans l'atomic, un rollback ferait disparaitre le user local pendant
        # que Fedow garde deja sa cle RSA ; au retry Fedow refuserait la nouvelle cle, et
        # cet email deviendrait indeclarable a vie.
        # / Resolve the membership's member BEFORE the atomic, for the same latency reason
        #   plus a heavier one: it DECLARES the member to Fedow. A rollback would drop the
        #   local user while Fedow keeps their RSA key, making that email undeclarable.
        try:
            adherent = _resoudre_adherent_hors_atomic(request, articles_normaux)
        except ValueError as erreur_adherent:
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": f"{erreur_adherent}",
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        produits_stock_negatif = []
        with db_transaction.atomic():
            # La vente du panier : ouverte en premier, encaissée en dernier, dans la
            # MEME transaction que les lignes. Si l'encaissement échoue, rien n'est
            # écrit. Sa clé d'idempotence est l'identifiant du paiement : un rejeu la
            # retrouve (_executer_avec_cle_idempotence).
            # / The cart's sale: opened first, settled last, in the SAME transaction.
            # Panier vide (tous les articles ont été écartés à la lecture) : rien n'est
            # vendu, aucune vente n'est ouverte, et la caisse répond par un succès sans
            # rien écrire. Le service refuse une vente sans article.
            # / Empty cart: nothing is sold, no sale is opened, a success writing nothing.
            vente = None
            panier_vide = len(articles_panier) == 0
            if not panier_vide:
                vente = _ouvrir_la_vente_de_caisse(
                    request,
                    point_de_vente,
                    uuid_transaction,
                    consigne_dans_panier,
                    carte_client,
                    adherent,
                )

            # Articles normaux (ventes, adhesions) → LigneArticle
            # Normal articles (sales, memberships) → LigneArticle
            lignes_normales = []
            if articles_normaux:
                lignes_normales, produits_stock_negatif = _creer_lignes_articles(
                    articles_normaux,
                    moyen_paiement_code,
                    uuid_transaction=uuid_transaction,
                    point_de_vente=point_de_vente,
                    vente=vente,
                )

            # Recharges AVANT les adhesions, et l'ordre compte.
            # `wallet_client` a ete resolu plus haut : pour une carte anonyme, c'est son
            # wallet ephemere. Or la fusion d'adhesion DETACHE ce wallet de la carte. Recharger
            # apres creditrait donc un wallet que plus rien ne reference — argent inaccessible.
            # En rechargeant d'abord, la fusion ramasse le solde tout juste credite.
            # / Top-ups BEFORE memberships, and the order matters: the membership merge
            #   DETACHES the ephemeral wallet, so topping up after would credit a wallet
            #   nothing references any more. Top up first, the merge then collects it.
            if articles_recharge:
                _executer_recharges(
                    articles_recharge,
                    wallet_client,
                    carte_client,
                    code_methode_paiement=moyen_paiement_code,
                    ip_client=ip_client,
                    point_de_vente=point_de_vente,
                    vente=vente,
                    uuid_transaction=uuid_transaction,
                )

            # Adhesions → creer les Memberships et les rattacher aux LigneArticle
            # Memberships → create Membership records and link them to LigneArticle
            _creer_adhesions_depuis_panier(
                request,
                articles_normaux,
                lignes_articles=lignes_normales,
                adherent=adherent,
            )

            # Billets → creer Reservation + Tickets et rattacher aux LigneArticle
            # Tickets → create Reservation + Tickets and link them to LigneArticle
            reservations_billets = _creer_billets_depuis_panier(
                request,
                articles_normaux,
                lignes_articles=lignes_normales,
            )

            # En DERNIER : les liens adhésion / billet sont posés sur les lignes, la
            # vente peut être réglée puis encaissée (elle ne se modifie plus ensuite).
            # / LAST: memberships and tickets are linked, the sale is paid and settled.
            if vente is not None:
                _regler_et_encaisser_la_vente_de_caisse(
                    vente, articles_panier, moyen_paiement_code
                )

        # Apres le bloc atomic : envoyer les billets par email via Celery.
        # Ne pas appeler dans le bloc atomic (si rollback, le mail partirait quand meme).
        # / After the atomic block: send tickets by email via Celery.
        # Do not call inside the atomic block (if rollback, email would still be sent).
        if reservations_billets:
            _envoyer_billets_par_email(reservations_billets)

        # Impression automatique des billets pour le PV BILLETTERIE
        # / Auto-print tickets for ticketing POS
        printer_de_ce_terminal = imprimante_du_terminal(request.user)
        if (
            reservations_billets
            and point_de_vente.comportement == PointDeVente.BILLETTERIE
            and printer_de_ce_terminal
        ):
            from BaseBillet.models import Ticket

            for reservation in reservations_billets:
                tickets_reservation = Ticket.objects.filter(
                    reservation=reservation,
                ).select_related("pricesold", "reservation__event")
                for ticket_obj in tickets_reservation:
                    imprimer_billet(
                        ticket_obj, reservation, reservation.event,
                        printer_de_ce_terminal,
                    )

        context = {
            "currency_data": CURRENCY_DATA,
            "payment": donnees_paiement,
            "monnaie_name": state["place"]["monnaie_name"],
            "moyen_paiement": PAYMENT_METHOD_TRANSLATIONS.get(moyen_paiement_code, ""),
            "deposit_is_present": consigne_dans_panier,
            "total": total_en_euros,
            "state": state,
            "original_payment": transaction_precedente,
            "uuid_transaction": str(uuid_transaction),
            "uuid_vente": _uuid_de_la_vente_du_paiement(uuid_transaction),
            "uuid_pv": str(point_de_vente.uuid),
            "produits_stock_negatif": produits_stock_negatif,
            # Avertissements du rattachement de carte (adhesion) : le caissier
            # doit savoir qu'une carte n'a pas ete rattachee, meme si la vente
            # a abouti. / Card-linking warnings: the cashier must know a card
            # was not attached, even though the sale went through.
            "avertissements_adhesion": adherent["avertissements"] if adherent else [],
        }
        return render(
            request, "laboutik/partial/hx_return_payment_success.html", context
        )

    # ------------------------------------------------------------------ #
    #  Flux de paiement : espèces                                         #
    #  Payment flow: cash                                                 #
    # ------------------------------------------------------------------ #

    def _payer_en_especes(
        self,
        request,
        state,
        donnees_paiement,
        articles_panier,
        total_en_euros,
        total_centimes,
        consigne_dans_panier,
        transaction_precedente,
        moyen_paiement_code,
        uuid_transaction_impose=None,
    ):
        """
        Paiement en espèces.
        Cash payment.

        LOCALISATION : laboutik/views.py

        Deux cas :
        1. Paiement exact (given_sum vide ou == 0) → succès immédiat
        2. Le caissier saisit la somme donnée → on calcule la monnaie à rendre

        Two cases:
        1. Exact payment (given_sum empty or == 0) → immediate success
        2. The cashier enters the given amount → we calculate the change
        """
        somme_donnee_en_centimes = donnees_paiement["given_sum"]

        # Recuperer le PV depuis les donnees de paiement (pour l'impression)
        # / Get the POS from payment data (for printing)
        uuid_pv = donnees_paiement.get("uuid_pv", "")
        point_de_vente = PointDeVente.objects.get(
            uuid=uuid_pv
        )

        # La somme est suffisante si :
        # - le caissier n'a rien saisi (= paiement exact, pas de monnaie à rendre)
        # - ou la somme donnée couvre le total
        # The amount is sufficient if:
        # - the cashier entered nothing (= exact payment, no change to give)
        # - or the given sum covers the total
        somme_est_suffisante = (
            somme_donnee_en_centimes == 0 or somme_donnee_en_centimes >= total_centimes
        )

        if somme_est_suffisante:
            ip_client = request.META.get("REMOTE_ADDR", "0.0.0.0")

            # Identifiant unique de ce paiement (cle d'idempotence si fournie)
            # / Unique ID for this payment (idempotency key when provided)
            uuid_transaction = uuid_transaction_impose or uuid_module.uuid4()

            # Séparer articles normaux et recharges
            # Separate normal articles and top-ups
            articles_normaux = [
                a
                for a in articles_panier
                if a["product"].methode_caisse not in METHODES_RECHARGE
            ]
            articles_recharge = [
                a
                for a in articles_panier
                if a["product"].methode_caisse in METHODES_RECHARGE
            ]
            reservations_billets = []

            # Validation amont du stock pour les articles normaux.
            # / Upstream stock validation for normal articles.
            erreurs_stock = _valider_stock_panier(articles_normaux)
            if erreurs_stock:
                return render(
                    request,
                    "laboutik/partial/hx_messages.html",
                    {
                        "action": "initUrlAddition();",
                        "msg_type": "warning",
                        "msg_content": _formater_erreurs_stock(erreurs_stock),
                    },
                    status=400,
                )

            # Resolution du wallet client AVANT le bloc atomic : _obtenir_ou_creer_wallet
            # peut faire un appel reseau Fedow (latence). Le faire DANS l'atomic
            # tiendrait un verrou DB pendant toute la latence reseau.
            # / Resolve the client wallet BEFORE the atomic block: _obtenir_ou_creer_wallet
            # may do a Fedow network call (latency). Doing it INSIDE the atomic would
            # hold a DB lock for the whole network latency.
            carte_client = None
            wallet_client = None
            if articles_recharge:
                tag_id_client = request.POST.get("tag_id", "").upper().strip()
                if not tag_id_client:
                    raise ValueError(_("Tag NFC client requis pour les recharges"))

                carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
                wallet_client = _obtenir_ou_creer_wallet(carte_client)

            # Resolution du membre d'une adhesion AVANT le bloc atomic, pour la meme raison
            # de latence — et une de plus, qui pese lourd : cette resolution DECLARE le
            # membre a Fedow. Faite dans l'atomic, un rollback ferait disparaitre le user
            # local pendant que Fedow garde deja sa cle RSA ; au retry Fedow refuserait la
            # nouvelle cle, et cet email deviendrait indeclarable a vie.
            # / Resolve the membership's member BEFORE the atomic: it DECLARES the member to
            #   Fedow, and a rollback would drop the local user while Fedow keeps their key.
            try:
                adherent = _resoudre_adherent_hors_atomic(request, articles_normaux)
            except ValueError as erreur_adherent:
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": f"{erreur_adherent}",
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request,
                    "laboutik/partial/hx_messages.html",
                    context_erreur,
                    status=400,
                )

            produits_stock_negatif = []
            # Créer les lignes articles en base (atomique)
            # Create article lines in DB (atomic)
            with db_transaction.atomic():
                # La vente du panier : ouverte en premier, encaissée en dernier, dans
                # la MEME transaction que les lignes. Un retour de consigne en espèces
                # est une vente AVOIR (argent rendu).
                # / The cart's sale: opened first, settled last, same transaction.
                # Panier vide (tous les articles ont été écartés à la lecture) : rien n'est
                # vendu, aucune vente n'est ouverte, et la caisse répond par un succès sans
                # rien écrire. Le service refuse une vente sans article.
                # / Empty cart: nothing is sold, no sale is opened, a success writing nothing.
                vente = None
                panier_vide = len(articles_panier) == 0
                if not panier_vide:
                    vente = _ouvrir_la_vente_de_caisse(
                        request,
                        point_de_vente,
                        uuid_transaction,
                        consigne_dans_panier,
                        carte_client,
                        adherent,
                    )

                # Articles normaux (ventes, adhesions) → LigneArticle
                # Normal articles (sales, memberships) → LigneArticle
                lignes_normales = []
                if articles_normaux:
                    lignes_normales, produits_stock_negatif = _creer_lignes_articles(
                        articles_normaux,
                        moyen_paiement_code,
                        uuid_transaction=uuid_transaction,
                        point_de_vente=point_de_vente,
                        vente=vente,
                    )

                # Recharges AVANT les adhesions, et l'ordre compte.
                # `wallet_client` a ete resolu plus haut : pour une carte anonyme, c'est son
                # wallet ephemere. Or la fusion d'adhesion DETACHE ce wallet de la carte.
                # Recharger apres creditrait donc un wallet que plus rien ne reference —
                # argent inaccessible. En rechargeant d'abord, la fusion ramasse le solde
                # tout juste credite.
                # / Top-ups BEFORE memberships: the membership merge DETACHES the ephemeral
                #   wallet, so topping up after would credit an unreferenced wallet.
                if articles_recharge:
                    _executer_recharges(
                        articles_recharge,
                        wallet_client,
                        carte_client,
                        code_methode_paiement=moyen_paiement_code,
                        ip_client=ip_client,
                        point_de_vente=point_de_vente,
                        vente=vente,
                        uuid_transaction=uuid_transaction,
                    )

                # Adhesions → creer les Memberships et les rattacher aux LigneArticle
                # Memberships → create Membership records and link them to LigneArticle
                _creer_adhesions_depuis_panier(
                    request,
                    articles_normaux,
                    lignes_articles=lignes_normales,
                    adherent=adherent,
                )

                # Billets → creer Reservation + Tickets et rattacher aux LigneArticle
                # Tickets → create Reservation + Tickets and link them to LigneArticle
                reservations_billets = _creer_billets_depuis_panier(
                    request,
                    articles_normaux,
                    lignes_articles=lignes_normales,
                )

                # En DERNIER : la vente est réglée puis encaissée.
                # / LAST: the sale is paid and settled.
                if vente is not None:
                    _regler_et_encaisser_la_vente_de_caisse(
                        vente, articles_panier, moyen_paiement_code
                    )

            # Apres le bloc atomic : envoyer les billets par email via Celery
            # / After the atomic block: send tickets by email via Celery
            if reservations_billets:
                _envoyer_billets_par_email(reservations_billets)

            # Impression automatique des billets pour le PV BILLETTERIE
            # / Auto-print tickets for ticketing POS
            printer_de_ce_terminal = imprimante_du_terminal(request.user)
            if (
                reservations_billets
                and point_de_vente.comportement == PointDeVente.BILLETTERIE
                and printer_de_ce_terminal
            ):
                for reservation in reservations_billets:
                    tickets_reservation = Ticket.objects.filter(
                        reservation=reservation,
                    ).select_related("pricesold", "reservation__event")
                    for ticket_obj in tickets_reservation:
                        imprimer_billet(
                            ticket_obj, reservation, reservation.event,
                            printer_de_ce_terminal,
                        )

            # Calculer la monnaie à rendre (en euros)
            # Calculate change to give back (in euros)
            donnees_paiement["give_back"] = 0
            if somme_donnee_en_centimes > total_centimes:
                donnees_paiement["give_back"] = (
                    somme_donnee_en_centimes - total_centimes
                ) / 100

            context = {
                "currency_data": CURRENCY_DATA,
                "payment": donnees_paiement,
                "monnaie_name": state["place"]["monnaie_name"],
                "moyen_paiement": PAYMENT_METHOD_TRANSLATIONS.get(
                    moyen_paiement_code, ""
                ),
                "deposit_is_present": consigne_dans_panier,
                "total": total_en_euros,
                "state": state,
                "original_payment": transaction_precedente,
                "uuid_transaction": str(uuid_transaction),
                "uuid_vente": _uuid_de_la_vente_du_paiement(uuid_transaction),
                "uuid_pv": str(point_de_vente.uuid),
                "produits_stock_negatif": produits_stock_negatif,
                # Avertissements du rattachement de carte (adhesion) : le caissier
                # doit savoir qu'une carte n'a pas ete rattachee, meme si la vente
                # a abouti. / Card-linking warnings: the cashier must know a card
                # was not attached, even though the sale went through.
                "avertissements_adhesion": adherent["avertissements"] if adherent else [],
            }
            return render(
                request, "laboutik/partial/hx_return_payment_success.html", context
            )

        # Somme insuffisante → ne rien faire (le JS gère la validation côté client)
        # Insufficient amount → do nothing (JS handles client-side validation)
        # « action » remet l'URL du formulaire sur moyens_paiement a la fermeture.
        # Sans elle, le prochain VALIDER repostait direct vers /payer/.
        # / "action" resets the form URL on close, or the next VALIDATE re-posts to /payer/.
        context_erreur = {
            "action": "initUrlAddition();",
            "msg_type": "warning",
            "msg_content": _("Il y a une erreur !"),
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context_erreur)

    # ------------------------------------------------------------------ #
    #  Flux de paiement : retour de consigne sur la carte du client        #
    #  Payment flow: deposit return onto the customer's card               #
    # ------------------------------------------------------------------ #

    def _rembourser_consigne_par_nfc(
        self,
        request,
        state,
        donnees_paiement,
        articles_panier,
        total_en_euros,
        point_de_vente,
        uuid_transaction_impose=None,
    ):
        """
        Rembourse une consigne sur la carte du client : une RECHARGE, pas un débit.
        / Refunds a deposit onto the customer's card: a TOP-UP, not a debit.

        LOCALISATION : laboutik/views.py

        POURQUOI UN FLUX A PART / WHY A SEPARATE FLOW :
        `_payer_par_nfc` cherche de quoi PRELEVER, en descendant une cascade d'assets.
        Un montant négatif n'a pas de sens pour elle : sa boucle s'arrête au premier
        tour (`reste_article <= 0`) et n'écrit rien du tout — ni débit, ni ligne, tout
        en affichant un écran de succès. Rendre de l'argent est l'opération inverse, et
        elle mérite son propre chemin, court et lisible.
        La V1 fait le même choix (`LaBoutik/webview/views.py`, `methode_CR` :
        `refill_wallet(abs(total))`).

        FLUX :
        1. Retrouver la carte présentée et son portefeuille (hors transaction : la
           résolution du portefeuille peut interroger Fedow par le réseau)
        2. Vérifier que la monnaie à créditer est désignée et qu'elle est locale
        3. Dans UNE transaction : créditer le portefeuille, puis écrire la ligne
           comptable au montant négatif

        Le crédit et la ligne sont dans la MÊME transaction, et ce n'est pas un détail :
        `TransactionService.creer_recharge` est une écriture en base, pas un appel
        réseau. Les séparer laisserait passer le cas « le client est crédité, la ligne
        comptable échoue » — de la monnaie créée sans trace.
        / The credit and the line share ONE transaction: creer_recharge is a local DB
          write, not a network call. Splitting them would allow credited money with no
          accounting trace.

        :param articles_panier: articles du panier, tous des retours de consigne
        :param total_en_euros: total déjà passé en valeur absolue par payer()
        :return: la réponse HTTP du POS
        """
        # --- 1. La carte présentée ---
        # / The tapped card.
        tag_id_client = request.POST.get("tag_id", "").upper().strip()
        if not tag_id_client:
            return self._refuser_le_retour_de_consigne(
                request, _("Carte du client requise pour rembourser une consigne.")
            )

        try:
            carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
        except CarteCashless.DoesNotExist:
            return self._refuser_le_retour_de_consigne(
                request, _("Carte inconnue.")
            )

        # Hors transaction : cette résolution peut interroger Fedow par le réseau.
        # / Outside the transaction: this may query Fedow over the network.
        wallet_client = _obtenir_ou_creer_wallet(carte_client)

        # --- 2. La monnaie à créditer ---
        # La règle vit dans `_asset_de_retour_consigne`, partagée avec l'écran qui
        # propose le bouton CASHLESS : les deux doivent dire la même chose, sinon le
        # caissier voit un bouton menant à un refus certain.
        # / The rule lives in _asset_de_retour_consigne, shared with the screen that
        #   offers the CASHLESS button: both must agree.
        asset_a_crediter, raison_du_refus = _asset_de_retour_consigne(articles_panier)
        if asset_a_crediter is None:
            return self._refuser_le_retour_de_consigne(request, raison_du_refus)

        # --- 3. Créditer, puis écrire la ligne — dans la même transaction ---
        # / Credit, then write the line — in the same transaction.
        ip_client = request.META.get("REMOTE_ADDR", "0.0.0.0")
        # Cle d'idempotence de payer() si fournie / idempotency key when provided
        uuid_transaction = uuid_transaction_impose or uuid_module.uuid4()
        montant_a_rendre_centimes = abs(_calculer_total_panier_centimes(articles_panier))

        with db_transaction.atomic():
            # Un retour de consigne est un remboursement : une vente AVOIR, sans vente
            # liée (le gobelet est anonyme, D11). Ouverte en premier, encaissée en
            # dernier, dans la même transaction que le crédit de la carte.
            # / A deposit return is a refund: a CREDIT NOTE sale, no linked sale.
            vente = ouvrir_vente(
                origine=SaleOrigin.LABOUTIK,
                nature=Vente.Nature.AVOIR,
                point_de_vente=point_de_vente,
                operateur=_operateur_de_la_caisse(
                    request, request.POST.get("tag_id_cm", "")
                ),
                client=carte_client.user,
                carte=carte_client,
                idempotency_key=str(uuid_transaction),
            )

            transaction_de_recredit = TransactionService.creer_recharge(
                sender_wallet=asset_a_crediter.wallet_origin,
                receiver_wallet=wallet_client,
                asset=asset_a_crediter,
                montant_en_centimes=montant_a_rendre_centimes,
                tenant=connection.tenant,
                ip=ip_client,
            )
            # Le montant de la ligne reste NEGATIF (le prix du gobelet rendu). C'est ce
            # signe qui fait baisser le chiffre d'affaires cashless dans tous les
            # anciens rapports, sans une ligne de code de plus.
            # / The line amount stays NEGATIVE: that sign is what lowers cashless
            #   revenue in every old report.
            _creer_lignes_articles(
                articles_panier,
                "nfc",
                asset_uuid=asset_a_crediter.uuid,
                carte=carte_client,
                wallet=wallet_client,
                uuid_transaction=uuid_transaction,
                point_de_vente=point_de_vente,
                vente=vente,
            )

            # Le règlement est copié de la transaction de recrédit : son montant (rendu,
            # donc négatif) et son identifiant. Jamais recalculé depuis les lignes.
            # / The payment is copied from the re-credit transaction, never from lines.
            ajouter_reglement(
                vente,
                moyen=PaymentMethod.LOCAL_EURO,
                montant=-transaction_de_recredit.amount,
                asset=asset_a_crediter.uuid,
                carte=carte_client,
                wallet=wallet_client,
                fedow_transaction_uuid=transaction_de_recredit.uuid,
            )
            encaisser_vente(vente)

        context = {
            "currency_data": CURRENCY_DATA,
            "payment": donnees_paiement,
            "monnaie_name": state["place"]["monnaie_name"],
            "moyen_paiement": PAYMENT_METHOD_TRANSLATIONS.get("nfc", ""),
            "deposit_is_present": True,
            "total": total_en_euros,
            "state": state,
            "original_payment": None,
            "uuid_transaction": str(uuid_transaction),
            "uuid_vente": _uuid_de_la_vente_du_paiement(uuid_transaction),
            "uuid_pv": str(point_de_vente.uuid),
            "produits_stock_negatif": [],
            "avertissements_adhesion": [],
        }
        return render(
            request, "laboutik/partial/hx_return_payment_success.html", context
        )

    def _refuser_le_retour_de_consigne(self, request, message):
        """
        Refuse un retour de consigne en 400, sans rien écrire en base.
        / Refuses a deposit return with 400, writing nothing.

        LOCALISATION : laboutik/views.py

        Tous les refus de ce flux passent par ici : le caissier doit toujours recevoir
        un message lisible plutôt qu'une erreur technique, et l'appelant doit rendre la
        main immédiatement.
        / Every refusal of this flow goes through here.
        """
        context_erreur = {
            "action": "initUrlAddition();",
            "msg_type": "warning",
            "msg_content": message,
            "selector_bt_retour": "#messages",
        }
        return render(
            request, "laboutik/partial/hx_messages.html", context_erreur, status=400
        )

    # ------------------------------------------------------------------ #
    #  Flux de paiement : NFC / cashless                                  #
    #  Payment flow: NFC / cashless                                       #
    # ------------------------------------------------------------------ #

    def _payer_par_nfc(
        self,
        request,
        state,
        donnees_paiement,
        articles_panier,
        total_en_euros,
        total_centimes,
        consigne_dans_panier,
        moyen_paiement_code,
        point_de_vente,
        uuid_transaction_impose=None,
    ):
        """
        Paiement NFC (cashless) via fedow_core — cascade multi-asset.
        NFC (cashless) payment via fedow_core — multi-asset cascade.

        LOCALISATION : laboutik/views.py

        Flux complet / Full flow:
        1. Gardes : recharges payantes, carte inconnue, wallet introuvable
        2. Préparer les soldes cascade disponibles (TNF → TLF → FED)
        3. Classifier les articles (fiduciaire, non-fiduciaire, adhésion, recharge)
        4. Vérifier soldes non-fiduciaires (tout ou rien)
        5. Boucle cascade article par article (fiduciaires + adhésions)
        6. Si complémentaire nécessaire → écran fonds insuffisants
        7. Bloc atomic : recharges, débits non-fidu, débits cascade, LigneArticle, adhésions
        8. Succès : afficher soldes multi-asset
        """
        from collections import OrderedDict

        # ================================================================ #
        #  GARDES (inchangées)                                              #
        #  GUARDS (unchanged)                                               #
        # ================================================================ #

        # GARDE : le paiement NFC est interdit si le panier contient des recharges PAYANTES (RE).
        # Les recharges gratuites (RC/TM) sont auto-creditees et ne bloquent pas le NFC.
        # / GUARD: NFC payment forbidden if cart has PAID top-ups (RE).
        # Free top-ups (RC/TM) are auto-credited and don't block NFC.
        if _panier_contient_recharges_payantes(articles_panier):
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": _(
                    "Les recharges ne peuvent pas être payées en cashless"
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # GARDE STOCK : même contrôle que pour espèces / CB / chèque.
        # Avant, le paiement NFC ne vérifiait pas le stock du tout :
        # un article épuisé et bloquant était vendu quand même.
        # On vérifie ici, avant tout débit (le débit legacy plus bas n'est pas remboursable).
        # Les recharges gratuites n'ont pas de stock : même filtre que dans payer().
        # / STOCK GUARD: same check as cash/card/cheque. NFC skipped it entirely before.
        # Done before any debit.
        articles_hors_recharges = []
        for article_du_panier in articles_panier:
            if article_du_panier["product"].methode_caisse not in METHODES_RECHARGE:
                articles_hors_recharges.append(article_du_panier)
        erreurs_stock = _valider_stock_panier(articles_hors_recharges)
        if erreurs_stock:
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": _formater_erreurs_stock(erreurs_stock),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        tag_id_client = request.POST.get("tag_id", "").upper().strip()

        # Chercher la carte client par tag_id
        # / Find client card by tag_id
        try:
            carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
        except CarteCashless.DoesNotExist:
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": _("Carte inconnue"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur)

        # Déterminer le wallet client (get or create éphémère si besoin)
        # / Determine client wallet (get or create ephemeral if needed)
        wallet_client = _obtenir_ou_creer_wallet(carte_client)

        # GARDE ADHESION, LE PLUS TOT POSSIBLE : si le panier contient une adhesion, on
        # verifie DES MAINTENANT qu'on sait qui est le membre — avant le moindre debit.
        # Sans cette garde, une carte anonyme payait l'adhesion, le wallet etait debite, la
        # LigneArticle creee… et aucune Membership n'etait enregistree : le client payait
        # une adhesion qui n'existait pas, en silence.
        # Cette etape ne fait AUCUN appel reseau et n'ecrit rien d'irreversible : on peut
        # donc encore refuser proprement. La declaration au reseau, elle, attendra la
        # derniere seconde avant la transaction (voir plus bas).
        # / MEMBERSHIP GUARD, AS EARLY AS POSSIBLE: before any debit, check we know who the
        #   member is. Without it, an anonymous card paid for a membership, the wallet was
        #   debited, the sale line created… and no Membership recorded — the customer paid
        #   for a membership that never existed, silently.
        try:
            adherent_identifie = _identifier_adherent(request, articles_panier)
        except ValueError as erreur_adherent:
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": f"{erreur_adherent}",
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # ================================================================ #
        #  PHASE 1 : Préparer les soldes cascade fiduciaire disponibles     #
        #  PHASE 1: Prepare available fiduciary cascade balances             #
        # ================================================================ #

        tenant_courant = connection.tenant

        # Récupérer tous les assets accessibles du tenant (propres + fédérés)
        # / Get all accessible assets for the tenant (own + federated)
        assets_accessibles = AssetService.obtenir_assets_accessibles(tenant_courant)

        # Construire la cascade : pour chaque catégorie dans l'ordre fixe,
        # chercher le 1er asset actif et lire son solde.
        # / Build cascade: for each category in fixed order,
        # find the first active asset and read its balance.
        soldes_cascade = OrderedDict()
        has_any_fiduciary_asset = False

        for categorie_fiduciaire in ORDRE_CASCADE_FIDUCIAIRE:
            asset_pour_categorie = assets_accessibles.filter(
                category=categorie_fiduciaire,
            ).first()
            if asset_pour_categorie is not None:
                has_any_fiduciary_asset = True
                solde_asset = WalletService.obtenir_solde(
                    wallet=wallet_client, asset=asset_pour_categorie
                )
                if solde_asset > 0:
                    soldes_cascade[asset_pour_categorie] = solde_asset

        # ================================================================ #
        #  PHASE 2 : Classifier les articles                                #
        #  PHASE 2: Classify articles                                       #
        # ================================================================ #

        articles_fiduciaires = []
        articles_non_fiduciaires = []
        articles_adhesion = []
        articles_recharge_gratuite = []
        # Adhesions payees en points : debitees avec les articles non fiduciaires,
        # et creees avec les autres adhesions (phase 7e).
        # / Memberships paid in points: debited as non-fiduciary, created in 7e.
        adhesions_payees_en_points = []

        for article in articles_panier:
            produit = article["product"]
            prix_obj = article["price"]
            methode = produit.methode_caisse

            # Le tarif en points passe en PREMIER : une adhesion a 300 points ne
            # doit jamais partir dans la cascade des euros.
            # / Points price FIRST: a points membership must never reach the euro cascade.
            if _tarif_est_en_points(prix_obj):
                # La monnaie doit exister et avoir un moyen de paiement connu,
                # AVANT tout debit : un tarif en points sans monnaie, ou d'une
                # categorie absente du mapping, n'est jamais enregistre en euros.
                # / The currency must exist and map to a payment method, before any debit.
                monnaie_du_tarif_est_acceptee = (
                    prix_obj.asset is not None
                    and prix_obj.asset.category in MAPPING_ASSET_CATEGORY_PAYMENT_METHOD
                )
                if not monnaie_du_tarif_est_acceptee:
                    context_erreur = {
                        "action": "initUrlAddition();",
                        "msg_type": "warning",
                        "msg_content": _("Cette monnaie n'est pas acceptée à la caisse."),
                        "selector_bt_retour": "#messages",
                    }
                    return render(
                        request,
                        "laboutik/partial/hx_messages.html",
                        context_erreur,
                        status=400,
                    )
                # Prix non-fiduciaire (TIM, FID) : débit direct sur l'asset du prix
                # / Non-fiduciary price (TIM, FID): direct debit on the price's asset
                articles_non_fiduciaires.append(article)
                if produit.categorie_article == Product.ADHESION:
                    adhesions_payees_en_points.append(article)
            elif produit.categorie_article == Product.ADHESION:
                # Adhésion en euros : cascade fiduciaire
                # / Euro membership: fiduciary cascade
                articles_adhesion.append(article)
            elif methode in METHODES_RECHARGE_GRATUITES:
                # RC (cadeau) ou TM (temps) : crédit gratuit, pas de débit
                # / RC (gift) or TM (time): free credit, no debit
                articles_recharge_gratuite.append(article)
            else:
                # Vente classique fiduciaire (VT ou tout autre type)
                # / Standard fiduciary sale (VT or any other type)
                articles_fiduciaires.append(article)

        # Les articles fiduciaires + adhésions utilisent la cascade
        # / Fiduciary articles + memberships use the cascade
        articles_pour_cascade = articles_fiduciaires + articles_adhesion

        # Vérifier qu'il existe au moins un asset fiduciaire si on a des articles cascade
        # / Check that at least one fiduciary asset exists if we have cascade articles
        if articles_pour_cascade and not has_any_fiduciary_asset:
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": _("Monnaie locale non configurée"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur)

        # ================================================================ #
        #  PHASE 3 : Vérifier soldes non-fiduciaires (tout ou rien)         #
        #  PHASE 3: Check non-fiduciary balances (all or nothing)           #
        # ================================================================ #

        # Le solde est compare a la SOMME du panier, monnaie par monnaie : deux
        # articles a 300 points demandent 600 points, meme si chacun passe seul.
        # / The balance is compared to the cart SUM, currency by currency.
        montant_necessaire_par_asset = OrderedDict()
        for article_nf in articles_non_fiduciaires:
            asset_cible = article_nf["price"].asset
            montant_de_l_article = article_nf["prix_centimes"] * article_nf["quantite"]
            if asset_cible not in montant_necessaire_par_asset:
                montant_necessaire_par_asset[asset_cible] = 0
            montant_necessaire_par_asset[asset_cible] += montant_de_l_article

        for asset_cible, montant_necessaire in montant_necessaire_par_asset.items():
            solde_nf = WalletService.obtenir_solde(
                wallet=wallet_client, asset=asset_cible
            )
            if solde_nf < montant_necessaire:
                montant_manquant_nf = (montant_necessaire - solde_nf) / 100
                donnees_paiement["missing"] = montant_manquant_nf
                context_insuffisant = {
                    "currency_data": CURRENCY_DATA,
                    "payment": donnees_paiement,
                    "card": {"name": carte_client.tag_id},
                    # Reference courte « ·· 4F2A » et soldes en pastilles
                    # / Short reference and balances as pills
                    "carte_ref": carte_client.tag_id[-4:],
                    "soldes": _soldes_locaux_pour_affichage(wallet_client),
                    "monnaie_name": asset_cible.name,
                    # Il manque des points : le popup affiche leur nom, et ne
                    # propose aucun complement (ni especes, ni CB, ni 2e carte).
                    # / Missing points: the popup shows their name, no complement.
                    "nom_monnaie_du_panier_en_points": asset_cible.name,
                    "payments_accepted": {
                        "accepte_especes": False,
                        "accepte_carte_bancaire": False,
                    },
                    "uuid_transaction": "",
                }
                return render(
                    request,
                    "laboutik/partial/hx_funds_insufficient.html",
                    context_insuffisant,
                )

        # ================================================================ #
        #  PHASE 4 : Boucle cascade article par article                     #
        #  PHASE 4: Cascade loop article by article                         #
        # ================================================================ #

        # lignes_nfc : tuples (article_dict, asset_ou_none, amount_centimes, payment_method_code)
        # asset=None signifie « reste à payer en complémentaire ».
        # / asset=None means "remainder to pay as complement".
        lignes_nfc = []
        soldes_restants = OrderedDict()
        for asset_cascade, solde_cascade in soldes_cascade.items():
            soldes_restants[asset_cascade] = solde_cascade

        # Collecter les assets débités pour l'affichage final
        # / Collect debited assets for final display
        assets_debites = set()

        # Accumulateur des débits par asset pour l'affichage complémentaire
        # {asset: montant_total_debite_en_centimes}
        # / Accumulator of debits per asset for complement display
        debits_par_asset_pour_affichage = OrderedDict()

        for article_cascade in articles_pour_cascade:
            montant_total_article = (
                article_cascade["prix_centimes"] * article_cascade["quantite"]
            )
            reste_article = montant_total_article

            for asset_courant, solde_courant in soldes_restants.items():
                if reste_article <= 0:
                    break
                if solde_courant <= 0:
                    continue

                debit_sur_cet_asset = min(solde_courant, reste_article)
                payment_method_pour_asset = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[
                    asset_courant.category
                ]
                lignes_nfc.append(
                    (
                        article_cascade,
                        asset_courant,
                        debit_sur_cet_asset,
                        payment_method_pour_asset,
                    )
                )
                soldes_restants[asset_courant] -= debit_sur_cet_asset
                reste_article -= debit_sur_cet_asset
                assets_debites.add(asset_courant)

                # Accumuler le débit pour l'affichage complémentaire
                # / Accumulate debit for complement display
                if asset_courant not in debits_par_asset_pour_affichage:
                    debits_par_asset_pour_affichage[asset_courant] = 0
                debits_par_asset_pour_affichage[asset_courant] += debit_sur_cet_asset

            # S'il reste un montant non couvert → ligne complémentaire (asset=None)
            # / If there's an uncovered amount → complement line (asset=None)
            if reste_article > 0:
                lignes_nfc.append((article_cascade, None, reste_article, None))

        # ================================================================ #
        #  PHASE 5 : Calculer le total complémentaire                       #
        #  PHASE 5: Calculate complement total                              #
        # ================================================================ #

        total_complementaire = 0
        for _art, asset_ligne, amount_ligne, _pm in lignes_nfc:
            if asset_ligne is None:
                total_complementaire += amount_ligne

        # ================================================================ #
        #  CRAN LEGACY (C2) : FED + TLF fédérés du réseau comme cran de cascade  #
        # ================================================================ #
        # Après les monnaies locales, AVANT le complément. On regarde si le legacy (FED + TLF
        # fédérés, lu FRAIS sur Fedow) couvre TOUT le reste du panier. Si oui → sortie « couverte » :
        # le débit part à la validation (PHASE 7, hors atomic). Sinon, on ne touche à rien et le
        # complément reste (le legacy PARTIEL sera géré par payer_complementaire — C2.3).
        # / LEGACY tier: after locals, before complement. If the fresh legacy balance covers ALL the
        # remainder → "covered" sale (debit at validation). Otherwise keep the complement.
        legacy_couvre_tout = False
        montant_legacy = 0
        if total_complementaire > 0 and carte_client.user is not None:
            depensable_legacy, legacy_disponible = lire_depensable_fed_frais(carte_client.user)
            if legacy_disponible and depensable_legacy > 0:
                # Le legacy couvre ce qu'il peut (tout ou une PARTIE) ; le reste ira au complément.
                # / Legacy covers what it can (all or PART); the rest goes to the complement.
                montant_legacy = min(depensable_legacy, total_complementaire)
                total_complementaire -= montant_legacy
                if total_complementaire == 0:
                    # Couvert entièrement (locaux + legacy) → sortie « couverte » : débit à la
                    # validation (PHASE 7), on saute l'écran complément.
                    # / Fully covered → "covered" sale: debit at validation (PHASE 7).
                    legacy_couvre_tout = True
                # Sinon : legacy PARTIEL → l'écran complément s'affiche avec le reste réduit. Le
                # débit FED partiel se fera dans payer_complementaire (qui re-lit le FED frais).
                # / Otherwise: PARTIAL legacy → complement screen shows the reduced remainder; the
                # partial FED debit happens in payer_complementaire (which re-reads fresh FED).

        # =====================================================Type d'actif=========== #
        #  PHASE 6 : Si complémentaire > 0 → écran fonds insuffisants       #
        #  PHASE 6: If complement > 0 → insufficient funds screen           #
        # ================================================================ #

        if total_complementaire > 0:
            # Phase 6 : complémentaire nécessaire → afficher l'écran de choix
            # / Phase 6: complement needed → show choice screen

            import json as json_module

            # Préparer le détail cascade pour l'affichage
            # / Prepare cascade detail for display
            detail_cascade_affichage = []
            for asset_debite, montant_debite in debits_par_asset_pour_affichage.items():
                detail_cascade_affichage.append(
                    {
                        "name": asset_debite.name,
                        "montant_euros": f"{montant_debite / 100:.2f}",
                    }
                )

            # Le legacy PARTIEL (FED + TLF fédérés) couvre `montant_legacy` du reste : on l'affiche
            # dans le détail pour que le caissier voie ce qui est pris sur le réseau. Le débit réel
            # se fera à la validation (payer_complementaire, re-lecture fraîche du FED).
            # / Partial legacy covers `montant_legacy` of the remainder: show it in the detail.
            if montant_legacy > 0:
                detail_cascade_affichage.append(
                    {
                        "name": _("Réseau (FED)"),
                        "montant_euros": f"{montant_legacy / 100:.2f}",
                    }
                )

            # Sérialiser les données cascade pour propagation via hidden fields
            # / Serialize cascade data for propagation via hidden fields
            cascade_json = json_module.dumps(
                [
                    [str(asset.uuid), montant]
                    for asset, montant in debits_par_asset_pour_affichage.items()
                ]
            )

            total_nfc = sum(debits_par_asset_pour_affichage.values())

            context_complement = {
                "action": "initUrlAddition();",
                "tag_id_carte1": tag_id_client,
                "detail_cascade": detail_cascade_affichage,
                "cascade_carte1_json": cascade_json,
                "total_nfc_carte1": total_nfc,
                "total_nfc_carte1_euros": f"{total_nfc / 100:.2f}",
                "total_panier_euros": f"{total_centimes / 100:.2f}",
                "reste_euros": f"{total_complementaire / 100:.2f}",
                "accepte_especes": point_de_vente.accepte_especes,
                "accepte_carte_bancaire": point_de_vente.accepte_carte_bancaire,
                "autoriser_2eme_carte": True,
            }
            return render(
                request,
                "laboutik/partial/hx_complement_paiement.html",
                context_complement,
            )

        # ================================================================ #
        #  PHASE 7 : Bloc atomic complet (pas de complémentaire)            #
        #  PHASE 7: Full atomic block (no complement)                       #
        # ================================================================ #

        ip_client = request.META.get("REMOTE_ADDR", "0.0.0.0")
        # Cle d'idempotence de payer() si fournie / idempotency key when provided
        uuid_transaction = uuid_transaction_impose or uuid_module.uuid4()

        # ----- Débit LEGACY (HORS atomic : c'est un appel réseau) -----
        # Si le legacy couvre tout le reste, on le débite MAINTENANT, avant le bloc atomic local.
        # Fedow fait sa cascade (TLF fédérés → FED) et renvoie les transactions ; on les répartit
        # sur les articles non couverts en gardant chaque moyen DISTINCT (LOCAL_EURO vs STRIPE_FED).
        # Échec (solde baissé entre lecture et débit, réseau) → fail-fast : AUCUN débit local, on
        # invite à rescanner (le solde fait foi). On n'entre dans l'atomic qu'après un débit réussi.
        # / LEGACY debit (OUTSIDE atomic: network call). If it covers all the remainder, debit now.
        # Fail-fast on error: no local debit, ask to rescan.
        lignes_legacy = []
        transactions_legacy = []
        if legacy_couvre_tout:
            lignes_complement = [t for t in lignes_nfc if t[1] is None]
            try:
                transactions_legacy = _debiter_legacy(
                    carte_client.user, montant_legacy, uuid_transaction
                )
            except Exception as erreur_legacy:
                logger.warning(f"Débit legacy échoué (rescan demandé) : {erreur_legacy}")
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _("Le solde du réseau a changé, rescannez la carte"),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request, "laboutik/partial/hx_messages.html", context_erreur, status=409
                )
            lignes_legacy = _repartir_legacy_sur_articles(
                lignes_complement, transactions_legacy
            )
            # Les parts complément (asset=None) sont désormais couvertes par le legacy : on les
            # retire de lignes_nfc pour qu'elles ne soient ni recréées en double, ni laissées impayées.
            # / The complement parts are now covered by legacy: drop them from lignes_nfc.
            lignes_nfc = [t for t in lignes_nfc if t[1] is not None]

        # DECLARATION DU MEMBRE AU RESEAU — le plus tard possible, et hors transaction.
        # Hors transaction : un appel reseau sous verrou DB le tient pendant toute la
        # latence, et un rollback ferait disparaitre le membre local pendant que le reseau
        # garde deja sa cle RSA — cet email deviendrait indeclarable a vie.
        # Le plus tard possible : le debit du segment legacy, juste au-dessus, part sur le
        # reseau et NE SE REMBOURSE PAS. Declarer avant lui exposerait a un etat ou la carte
        # est liee sur le reseau alors que la vente s'arrete sur un solde insuffisant.
        # / DECLARE THE MEMBER TO THE NETWORK — as late as possible, outside the transaction.
        #   Outside: a network call under a DB lock holds it for the whole latency, and a
        #   rollback would drop the local member while the network keeps their RSA key.
        #   As late as possible: the legacy debit just above CANNOT be refunded.
        adherent = None
        if adherent_identifie is not None:
            user_adhesion, carte_adhesion = adherent_identifie
            try:
                adherent = _declarer_adherent_au_reseau(
                    user_adhesion, carte_adhesion, ip_client
                )
            except ValueError as erreur_adherent:
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": f"{erreur_adherent}",
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request,
                    "laboutik/partial/hx_messages.html",
                    context_erreur,
                    status=400,
                )

        # Le journal d'incident du débit legacy, préparé ici, AVANT le bloc atomic :
        # le débit du réseau est déjà fait et ne s'annule pas. Si le bloc échoue ensuite
        # (solde local insuffisant, égalité de la vente rompue), l'argent est prélevé
        # sur le réseau sans vente ni ligne : ce message permet de le régulariser à la
        # main (montant, carte, uuid de chaque transaction du réseau).
        # / The legacy-debit incident log, prepared BEFORE the atomic block: if the block
        #   fails, the network money is taken without a sale; this message allows a
        #   manual fix (amount, card, uuid of each network transaction).
        message_d_incident_legacy = ""
        if legacy_couvre_tout and lignes_legacy:
            uuids_des_transactions_legacy = []
            for transaction_legacy in transactions_legacy:
                uuids_des_transactions_legacy.append(str(transaction_legacy[3]))
            message_d_incident_legacy = (
                f"INCIDENT legacy débité sans LigneArticle (atomic local échoué) — "
                f"uuid_transaction={uuid_transaction} carte={carte_client.tag_id} "
                f"montant_legacy={montant_legacy} "
                f"transactions_legacy={', '.join(uuids_des_transactions_legacy)} : "
                f"régularisation manuelle requise."
            )

        try:
            with db_transaction.atomic():
                # ----- 7.0) Ouvrir la vente du paiement -----
                # Une seule vente pour tout le panier : articles en euros, en points,
                # recharges cadeau. La clé d'idempotence est l'identifiant du paiement,
                # le même que sur les lignes : un rejeu retrouve cette vente.
                # Panier en points (une seule monnaie, voir _monnaie_du_panier) : la vente
                # est tenue dans cette monnaie (`unite` = son uuid), sinon en euros.
                # Le client : l'adhérent identifié, sinon le titulaire de la carte.
                # Panier vide (tous les articles ont été écartés à la lecture) : rien
                # n'est vendu, aucune vente n'est ouverte, et la caisse répond par un
                # succès sans rien écrire. Le service refuse une vente sans article.
                # / One sale for the whole cart. The payment id is its idempotency key.
                #   Points cart: the sale's unit is the points currency.
                #   Empty cart: no sale is opened, a success writing nothing.
                unite_de_la_vente = "EUR"
                if articles_non_fiduciaires:
                    monnaie_du_panier_en_points = articles_non_fiduciaires[0]["price"].asset
                    unite_de_la_vente = str(monnaie_du_panier_en_points.uuid)

                client_de_la_vente = carte_client.user
                if adherent is not None:
                    client_de_la_vente = adherent["user"]

                vente = None
                panier_vide = len(articles_panier) == 0
                if not panier_vide:
                    vente = ouvrir_vente(
                        origine=SaleOrigin.LABOUTIK,
                        nature=Vente.Nature.VENTE,
                        unite=unite_de_la_vente,
                        point_de_vente=point_de_vente,
                        operateur=_operateur_de_la_caisse(
                            request, request.POST.get("tag_id_cm", "")
                        ),
                        client=client_de_la_vente,
                        carte=carte_client,
                        idempotency_key=str(uuid_transaction),
                    )

                # ----- 7a) Crédits recharges gratuites AVANT les débits -----
                # Les recharges sont des articles de la MÊME vente, avec l'identifiant
                # du paiement sur leurs lignes.
                # / Free top-up credits BEFORE debits, items of the SAME sale.
                if articles_recharge_gratuite:
                    _executer_recharges(
                        articles_recharge_gratuite,
                        wallet_client,
                        carte_client,
                        code_methode_paiement="gift",
                        ip_client=ip_client,
                        point_de_vente=point_de_vente,
                        vente=vente,
                        uuid_transaction=uuid_transaction,
                    )

                # ----- 7b) Débits non-fiduciaires (direct sur asset du prix) -----
                # Une transaction par article, et un règlement par transaction : son
                # montant et son uuid sont COPIÉS de la transaction renvoyée.
                # / Non-fiduciary debits: one transaction per item, one payment per
                #   transaction, copied from the returned transaction.
                lignes_non_fidu = []
                for article_nf in articles_non_fiduciaires:
                    asset_nf_cible = article_nf["price"].asset
                    montant_nf = article_nf["prix_centimes"] * article_nf["quantite"]
                    transaction_en_points = TransactionService.creer_vente(
                        sender_wallet=wallet_client,
                        receiver_wallet=asset_nf_cible.wallet_origin,
                        asset=asset_nf_cible,
                        montant_en_centimes=montant_nf,
                        tenant=tenant_courant,
                        card=carte_client,
                        ip=ip_client,
                    )
                    pm_nf = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[
                        asset_nf_cible.category
                    ]
                    ajouter_reglement(
                        vente,
                        moyen=pm_nf,
                        montant=transaction_en_points.amount,
                        asset=asset_nf_cible.uuid,
                        carte=carte_client,
                        wallet=wallet_client,
                        fedow_transaction_uuid=transaction_en_points.uuid,
                    )
                    lignes_non_fidu.append(
                        (article_nf, asset_nf_cible, montant_nf, pm_nf)
                    )
                    assets_debites.add(asset_nf_cible)

                # ----- 7c) Débits fiduciaires cascade -----
                # Regrouper par asset pour faire 1 seule TransactionService.creer_vente par asset.
                # / Group by asset to make 1 single TransactionService.creer_vente per asset.
                debits_par_asset = OrderedDict()
                for _art_c, asset_c, amount_c, _pm_c in lignes_nfc:
                    if asset_c is not None:
                        if asset_c not in debits_par_asset:
                            debits_par_asset[asset_c] = 0
                        debits_par_asset[asset_c] += amount_c

                # Un règlement par transaction : son montant et son uuid sont COPIÉS de
                # la transaction renvoyée, jamais recalculés depuis les parts. Jetons
                # cadeau : règlement « jetons » (LG), un vrai règlement (il solde la
                # dette du lieu, D8 bis).
                # / One payment per transaction, copied from it. Gift tokens: LG payment.
                for asset_a_debiter, total_debit_asset in debits_par_asset.items():
                    transaction_de_la_monnaie = TransactionService.creer_vente(
                        sender_wallet=wallet_client,
                        receiver_wallet=asset_a_debiter.wallet_origin,
                        asset=asset_a_debiter,
                        montant_en_centimes=total_debit_asset,
                        tenant=tenant_courant,
                        card=carte_client,
                        ip=ip_client,
                    )
                    ajouter_reglement(
                        vente,
                        moyen=MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[
                            asset_a_debiter.category
                        ],
                        montant=transaction_de_la_monnaie.amount,
                        asset=asset_a_debiter.uuid,
                        carte=carte_client,
                        wallet=wallet_client,
                        fedow_transaction_uuid=transaction_de_la_monnaie.uuid,
                    )

                # ----- 7c bis) Règlements du débit legacy (fait plus haut, hors atomic) -----
                # Un règlement par transaction du réseau, lu dans `transactions_legacy` et
                # non dans les parts (une part a perdu le lien avec sa transaction). La
                # transaction vit sur le serveur Fedow distant : son uuid va dans
                # `reference_externe` (`fedow_transaction_uuid` est réservé aux
                # transactions `fedow_core` locales).
                # / One payment per network transaction, read from transactions_legacy.
                #   Remote transaction: its uuid goes to reference_externe.
                for transaction_legacy in transactions_legacy:
                    asset_legacy_uuid = transaction_legacy[0]
                    montant_legacy_de_la_transaction = transaction_legacy[1]
                    moyen_legacy = transaction_legacy[2]
                    uuid_de_la_transaction_legacy = transaction_legacy[3]
                    ajouter_reglement(
                        vente,
                        moyen=moyen_legacy,
                        montant=montant_legacy_de_la_transaction,
                        asset=asset_legacy_uuid,
                        carte=carte_client,
                        reference_externe=str(uuid_de_la_transaction_legacy),
                    )

                # ----- 7d) Créer toutes les LigneArticle (non-fidu + cascade locale + legacy) -----
                # Les lignes_legacy (FED/TLF fédérés débités plus haut hors atomic) portent déjà
                # leur moyen de paiement résolu (LOCAL_EURO / STRIPE_FED) et l'uuid de l'asset distant.
                # Chaque part est un article de la vente.
                # / Create all LigneArticle (non-fidu + local cascade + legacy lines), each
                #   part an item of the sale.
                toutes_les_lignes_pre_calculees = (
                    lignes_non_fidu + lignes_nfc + lignes_legacy
                )
                lignes_creees, produits_stock_negatif = _creer_lignes_articles_cascade(
                    lignes_pre_calculees=toutes_les_lignes_pre_calculees,
                    carte=carte_client,
                    wallet=wallet_client,
                    uuid_transaction=uuid_transaction,
                    point_de_vente=point_de_vente,
                    vente=vente,
                )

                # ----- 7e) Adhésions : créer Membership, rattacher à la 1ère LigneArticle -----
                # Adhesions payees en euros (cascade) et en points (non fiduciaires).
                # / Memberships: create Membership, link to first LigneArticle
                adhesions_a_creer = articles_adhesion + adhesions_payees_en_points
                if adhesions_a_creer:
                    # Construire index LigneArticle par product_uuid
                    # / Build LigneArticle index by product_uuid
                    lignes_par_product = {}
                    for ligne_creee in lignes_creees:
                        product_uuid_str = str(
                            ligne_creee.pricesold.productsold.product.uuid
                        )
                        if product_uuid_str not in lignes_par_product:
                            lignes_par_product[product_uuid_str] = ligne_creee

                    # Le membre vient de la resolution faite hors transaction, PAS de
                    # `carte_client.user` : une carte anonyme y valait None, et
                    # `_creer_ou_renouveler_adhesion(None)` rendait None — le wallet etait
                    # debite et la ligne creee, mais aucune adhesion n'existait.
                    # / The member comes from the resolution done outside the transaction,
                    #   NOT from carte_client.user, which was None for an anonymous card.
                    membre_adhesion = adherent["user"]

                    # La fusion locale du wallet ephemere passe APRES les debits (7b/7c) :
                    # ceux-ci s'appuient sur `wallet_client`, qui EST le wallet ephemere de
                    # la carte. Fusionner avant les detacherait de leur source.
                    # / The local merge runs AFTER the debits, which rely on wallet_client —
                    #   the card's ephemeral wallet. Merging first would detach their source.
                    if adherent["fusion_locale_autorisee"] and carte_client is not None:
                        try:
                            CarteService.lier_a_user(
                                qrcode_uuid=carte_client.uuid,
                                user=membre_adhesion,
                                ip=ip_client,
                            )
                        except (
                            CarteIntrouvable,
                            CarteDejaLiee,
                            UserADejaCarte,
                            SoldeInsuffisant,
                        ) as erreur_liaison:
                            logger.warning(
                                f"Adhesion POS NFC : fusion locale de la carte "
                                f"{carte_client.tag_id} impossible : {erreur_liaison}"
                            )
                            adherent["avertissements"].append(_(
                                "La carte n'a pas pu etre rattachee au membre. L'adhesion "
                                "est bien enregistree, le solde de la carte est intact."
                            ))

                    for article_ad in adhesions_a_creer:
                        membership = _creer_ou_renouveler_adhesion(
                            membre_adhesion,
                            article_ad["product"],
                            article_ad["price"],
                        )
                        # Payee en points : l'adhesion garde le moyen NON_MONETAIRE,
                        # et `contribution_value` le prix du tarif, en unites de la
                        # monnaie (voir Membership.unite_de_la_contribution).
                        # / Paid in points: the membership says so; the value is in units.
                        if membership and _tarif_est_en_points(article_ad["price"]):
                            membership.payment_method = PaymentMethod.NON_MONETAIRE
                            membership.save(update_fields=["payment_method"])
                        if membership:
                            product_uuid_ad = str(article_ad["product"].uuid)
                            ligne_ad = lignes_par_product.get(product_uuid_ad)
                            if ligne_ad:
                                ligne_ad.membership = membership
                                ligne_ad.save(update_fields=["membership"])
                            _appliquer_les_effets_d_une_adhesion_vendue_en_caisse(
                                membership, ligne_ad
                            )

                # ----- 7f) Encaisser la vente, EN DERNIER -----
                # `encaisser_vente` vérifie les deux égalités et pose le numéro. Si elles
                # ne tiennent pas, il lève `EgaliteDeVenteRompue` : tout le bloc est
                # annulé (lignes, débits locaux, recharges, adhésions).
                # / Settle the sale, LAST: a broken equality rolls back the whole block.
                if vente is not None:
                    encaisser_vente(vente)

        except SoldeInsuffisant:
            # Race condition : solde a changé entre le check et le débit
            # / Race condition: balance changed between check and debit
            # INCIDENT rarissime : si le legacy a déjà été débité (hors atomic) et que l'atomic
            # local échoue ensuite, le FED/TLF fédéré est prélevé SANS LigneArticle. On le
            # JOURNALISE pour régularisation manuelle (le legacy n'est pas annulable automatiquement).
            # / Rare INCIDENT: legacy already debited but local atomic failed → log for manual fix.
            if message_d_incident_legacy:
                logger.error(message_d_incident_legacy)
            nom_monnaie_fallback = _("Monnaie locale")
            premier_asset_fallback = assets_accessibles.filter(
                category__in=[Asset.TLF, Asset.TNF, Asset.FED],
            ).first()
            if premier_asset_fallback:
                nom_monnaie_fallback = premier_asset_fallback.name

            donnees_paiement["missing"] = total_en_euros
            context_insuffisant = {
                "currency_data": CURRENCY_DATA,
                "payment": donnees_paiement,
                "card": {"name": carte_client.tag_id},
                # Reference courte « ·· 4F2A » et soldes en pastilles
                # / Short reference and balances as pills
                "carte_ref": carte_client.tag_id[-4:],
                "soldes": _soldes_locaux_pour_affichage(wallet_client),
                "monnaie_name": nom_monnaie_fallback,
                "payments_accepted": {
                    "accepte_especes": point_de_vente.accepte_especes,
                    "accepte_carte_bancaire": point_de_vente.accepte_carte_bancaire,
                },
                "uuid_transaction": "",
            }
            # Panier en points (une seule monnaie, voir _monnaie_du_panier) : le
            # manque est dans cette monnaie, et aucun complement n'est propose.
            # / Points cart: shortfall in that currency, no complement offered.
            if articles_non_fiduciaires:
                monnaie_du_panier_en_points = articles_non_fiduciaires[0]["price"].asset
                context_insuffisant["nom_monnaie_du_panier_en_points"] = (
                    monnaie_du_panier_en_points.name
                )
            return render(
                request,
                "laboutik/partial/hx_funds_insufficient.html",
                context_insuffisant,
            )

        except EgaliteDeVenteRompue as erreur_d_egalite:
            # Les règlements ne couvrent pas exactement les articles : le bloc atomic a
            # tout annulé (lignes, débits locaux, recharges, adhésions). Le débit legacy,
            # fait avant, reste : même journal d'incident que pour un solde insuffisant.
            # La caisse montre son écran d'erreur, jamais une erreur 500.
            # / Broken equality: the atomic block rolled everything back. The legacy
            #   debit stays: same incident log. The register shows its error screen.
            if message_d_incident_legacy:
                logger.error(message_d_incident_legacy)
            logger.error(
                f"Vente NFC refusée (égalité rompue) — uuid_transaction={uuid_transaction} "
                f"carte={carte_client.tag_id} : {erreur_d_egalite}"
            )
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": _(
                    "Le paiement n'a pas été enregistré : la vente est incohérente. "
                    "Prévenez un responsable du lieu."
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=409
            )

        except Exception as erreur_imprevue:
            # Toute AUTRE exception dans l'atomic (erreur du service, contrainte de la
            # base…) : le local est annulé, mais le débit du réseau, fait avant, reste
            # prélevé SANS vente ni ligne. On JOURNALISE l'incident avec le message
            # préparé avant l'atomic, plus l'exception, puis on relaie l'exception
            # (500 volontaire). Cet `except` vient APRÈS les deux autres : ils gardent
            # leur écran de la caisse.
            # / Any OTHER exception in the atomic: the network debit, done before, stays
            #   taken without a sale. Log the prepared incident message plus the
            #   exception, then re-raise (500). This `except` comes AFTER the other two.
            if message_d_incident_legacy:
                logger.error(
                    f"{message_d_incident_legacy} "
                    f"Exception imprévue dans l'atomic : {erreur_imprevue}"
                )
            raise

        # ================================================================ #
        #  PHASE 8 : Succès — soldes multi-asset                            #
        #  PHASE 8: Success — multi-asset balances                          #
        # ================================================================ #

        # Avant / apres de TOUS les assets débités (pas seulement TLF) :
        # non-fiduciaires + cascade locale. Le legacy (Fedow) n'est pas affiché.
        # / Before / after of ALL debited assets: non-fiduciary + local cascade.
        soldes_apres_paiement = _calculer_soldes_apres_paiement(
            wallet=wallet_client,
            lignes_debitees=lignes_non_fidu + lignes_nfc,
        )

        # Regroupement par carte pour l'ecran de succes (un cadre par carte)
        # / Grouped per card for the success screen (one frame per card)
        cartes_apres_paiement = []
        if soldes_apres_paiement:
            cartes_apres_paiement.append(
                {"tag_id": carte_client.tag_id, "soldes": soldes_apres_paiement}
            )

        # Pour la rétro-compatibilité du template, on passe aussi le solde
        # du 1er asset débité comme nouveau_solde et monnaie_name.
        # / For template backward compatibility, also pass the first
        # debited asset's balance as nouveau_solde and monnaie_name.
        nouveau_solde_euros = None
        nom_monnaie_principal = ""
        if soldes_apres_paiement:
            nouveau_solde_euros = soldes_apres_paiement[0]["solde_euros"]
            nom_monnaie_principal = soldes_apres_paiement[0]["name"]

        # Panier en points (une seule monnaie) : le total paye s'ecrit dans cette
        # monnaie. Vide pour un panier en euros.
        # / Points cart: the paid total is written in that currency.
        nom_monnaie_du_panier_en_points = ""
        if articles_non_fiduciaires:
            nom_monnaie_du_panier_en_points = articles_non_fiduciaires[0]["price"].asset.name

        context = {
            "currency_data": CURRENCY_DATA,
            "payment": donnees_paiement,
            "monnaie_name": nom_monnaie_principal,
            "moyen_paiement": PAYMENT_METHOD_TRANSLATIONS.get(moyen_paiement_code, ""),
            "deposit_is_present": consigne_dans_panier,
            "total": total_en_euros,
            "nom_monnaie_du_panier_en_points": nom_monnaie_du_panier_en_points,
            # Total du panier recalcule par le serveur, en centimes (ou centiemes
            # de points) : l'ecran l'affiche pour un panier en points.
            # / Server-computed cart total, in cents (or hundredths of points).
            "total_du_panier_centimes": total_centimes,
            "state": state,
            "original_payment": None,
            # Données spécifiques NFC / NFC-specific data
            "nouveau_solde": nouveau_solde_euros,
            "card_name": carte_client.tag_id,
            "uuid_transaction": str(uuid_transaction),
            "uuid_vente": _uuid_de_la_vente_du_paiement(uuid_transaction),
            "uuid_pv": str(point_de_vente.uuid),
            # Multi-asset : liste des soldes après paiement
            # / Multi-asset: list of balances after payment
            "soldes_apres_paiement": soldes_apres_paiement,
            "cartes_apres_paiement": cartes_apres_paiement,
            "produits_stock_negatif": produits_stock_negatif,
            # Avertissements du rattachement de carte (adhesion) : le caissier doit savoir
            # qu'une carte n'a pas ete rattachee, meme si la vente a abouti.
            # / Card-linking warnings: the cashier must know a card was not attached.
            "avertissements_adhesion": adherent["avertissements"] if adherent else [],
        }
        return render(
            request, "laboutik/partial/hx_return_payment_success.html", context
        )

    # ----------------------------------------------------------------------- #
    #  Flow identification client : identification obligatoire avant paiement  #
    #  Client identification flow: mandatory identification before payment     #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["get"],
        url_path="lire_nfc_client",
        url_name="lire_nfc_client",
    )
    def lire_nfc_client(self, request):
        """
        GET /laboutik/paiement/lire_nfc_client/
        Attente NFC pour identification client. Apres scan, POST vers identifier_client.
        / NFC read wait for client identification. After scan, POST to identifier_client.

        LOCALISATION : laboutik/views.py

        Les flags du panier (panier_a_recharges, panier_a_adhesions, moyens_paiement)
        sont propages via query params depuis hx_display_type_payment.html.
        / Cart flags are propagated via query params from hx_display_type_payment.html.
        """
        panier_a_recharges = request.GET.get("panier_a_recharges", "")
        panier_a_adhesions = request.GET.get("panier_a_adhesions", "")
        panier_a_billets = request.GET.get("panier_a_billets", "")
        moyens_paiement_csv = request.GET.get("moyens_paiement", "")
        context = {
            "panier_a_recharges": panier_a_recharges,
            "panier_a_adhesions": panier_a_adhesions,
            "panier_a_billets": panier_a_billets,
            "moyens_paiement_csv": moyens_paiement_csv,
        }
        return render(request, "laboutik/partial/hx_lire_nfc_client.html", context)

    @action(
        detail=False,
        methods=["get"],
        url_path="formulaire_identification_client",
        url_name="formulaire_identification_client",
    )
    def formulaire_identification_client(self, request):
        """
        GET /laboutik/paiement/formulaire_identification_client/
        Affiche le formulaire email/nom/prenom vierge pour identifier le client.
        / Displays the blank email/name form for client identification.

        LOCALISATION : laboutik/views.py

        Les flags du panier sont propages via query params.
        / Cart flags are propagated via query params.
        """
        panier_a_recharges = request.GET.get("panier_a_recharges", "")
        panier_a_adhesions = request.GET.get("panier_a_adhesions", "")
        panier_a_billets = request.GET.get("panier_a_billets", "")
        moyens_paiement_csv = request.GET.get("moyens_paiement", "")
        context = {
            "panier_a_recharges": panier_a_recharges,
            "panier_a_adhesions": panier_a_adhesions,
            "panier_a_billets": panier_a_billets,
            "moyens_paiement_csv": moyens_paiement_csv,
        }
        return render(
            request,
            "laboutik/partial/hx_formulaire_identification_client.html",
            context,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="identifier_client",
        url_name="identifier_client",
    )
    def identifier_client(self, request):
        """
        POST /laboutik/paiement/identifier_client/

        Recoit tag_id (scan NFC) OU email/nom/prenom (formulaire).
        Le POST contient aussi les repid-* (articles du panier) et uuid_pv,
        car le formulaire soumis est #addition-form (qui contient tout).

        Retourne :
        - Si user identifie → hx_display_type_payment.html, mode client_identifie
          (resume articles + tuiles de paiement)
        - Si carte anonyme → hx_formulaire_identification_client.html (pre-rempli avec tag_id)
        - Si formulaire soumis avec email → validation puis meme popup (client_identifie)

        Receives tag_id (NFC scan) OR email/name (form).
        POST also contains repid-* (cart articles) and uuid_pv,
        because the submitted form is #addition-form (which contains everything).

        Returns:
        - If user identified → hx_display_type_payment.html in client_identifie mode
        - If anonymous card → hx_formulaire_identification_client.html (pre-filled with tag_id)
        - If form submitted with email → validation then the same popup

        LOCALISATION : laboutik/views.py
        """
        tag_id = request.POST.get("tag_id", "").upper().strip()
        email = request.POST.get("email_adhesion", "").strip().lower()
        prenom = request.POST.get("prenom_adhesion", "").strip()
        nom = request.POST.get("nom_adhesion", "").strip()

        # Flags du panier propages depuis les templates precedents (champs hidden)
        # / Cart flags propagated from previous templates (hidden fields)
        panier_a_recharges = request.POST.get("panier_a_recharges", "") == "True"
        panier_a_adhesions = request.POST.get("panier_a_adhesions", "") == "True"
        panier_a_billets = request.POST.get("panier_a_billets", "") == "True"
        moyens_paiement_csv = request.POST.get("moyens_paiement", "")
        moyens_paiement = [
            m.strip() for m in moyens_paiement_csv.split(",") if m.strip()
        ]

        # --- Reconstruire le panier depuis les repid-* du POST ---
        # Le #addition-form contient les articles (repid-*) et le PV (uuid_pv).
        # On les extrait pour afficher le recapitulatif article par article.
        # / Rebuild the cart from repid-* in POST data.
        # #addition-form contains articles (repid-*) and PV (uuid_pv).
        # We extract them to display the per-article recap.
        articles_panier = []
        total_en_euros = 0
        total_centimes = 0
        point_de_vente = None
        uuid_pv = request.POST.get("uuid_pv")
        if uuid_pv:
            try:
                point_de_vente = PointDeVente.objects.get(uuid=uuid_pv)
                articles_panier = _extraire_articles_du_panier(
                    request.POST, point_de_vente
                )
                total_centimes = _calculer_total_panier_centimes(articles_panier)
                total_en_euros = total_centimes / 100
            except (PointDeVente.DoesNotExist, ValueError):
                pass

        user = None
        carte = None

        # Option 1 : scan NFC — chercher la carte et son user
        # / Option 1: NFC scan — find the card and its user
        if tag_id:
            try:
                carte = CarteCashless.objects.get(tag_id=tag_id)
                user = carte.user
            except CarteCashless.DoesNotExist:
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _("Carte inconnue"),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request, "laboutik/partial/hx_messages.html", context_erreur
                )

        # Option 2 : formulaire email — valider avec le serializer
        # / Option 2: email form — validate with serializer
        if email and not user:
            serializer = ClientIdentificationSerializer(data=request.POST)
            if not serializer.is_valid():
                # Premiere erreur trouvee pour l'affichage
                # / First error found for display
                premiere_erreur = ""
                for champ, erreurs in serializer.errors.items():
                    premiere_erreur = erreurs[0]
                    break
                context = {
                    "tag_id": tag_id,
                    "email": email,
                    "prenom": prenom,
                    "nom": nom,
                    "erreur": premiere_erreur,
                    "panier_a_recharges": panier_a_recharges,
                    "panier_a_adhesions": panier_a_adhesions,
                    "panier_a_billets": panier_a_billets,
                    "moyens_paiement_csv": moyens_paiement_csv,
                }
                return render(
                    request,
                    "laboutik/partial/hx_formulaire_identification_client.html",
                    context,
                )

            email = serializer.validated_data["email_adhesion"]
            prenom = serializer.validated_data["prenom_adhesion"]
            nom = serializer.validated_data["nom_adhesion"]

            user = get_or_create_user(email, send_mail=False)
            # Mettre a jour prenom/nom si pas deja renseignes
            # / Update first/last name if not already set
            nom_ou_prenom_modifie = False
            if prenom and not user.first_name:
                user.first_name = prenom
                nom_ou_prenom_modifie = True
            if nom and not user.last_name:
                user.last_name = nom
                nom_ou_prenom_modifie = True
            if nom_ou_prenom_modifie:
                user.save(update_fields=["first_name", "last_name"])

        # ------------------------------------------------------------------
        # COURT-CIRCUIT : panier avec UNIQUEMENT des recharges gratuites (RC/TM)
        # et une carte scannee (user ou anonyme).
        # Pas de paiement necessaire → on credite immediatement et on affiche le succes.
        # Les RC/TM sont des cadeaux : le caissier scanne la carte et c'est tout.
        #
        # SHORT-CIRCUIT: cart with ONLY free top-ups (RC/TM) and a scanned card.
        # No payment needed → credit immediately and show success.
        # RC/TM are gifts: the cashier scans the card and that's it.
        # ------------------------------------------------------------------
        panier_uniquement_gratuit = _panier_contient_uniquement_recharges_gratuites(
            articles_panier
        )
        if carte and panier_uniquement_gratuit:
            ip_client = request.META.get("REMOTE_ADDR", "0.0.0.0")
            wallet_client = _obtenir_ou_creer_wallet(carte)

            with db_transaction.atomic():
                # Une vente ordinaire, sans règlement d'argent : la recharge cadeau est
                # un article hors chiffre d'affaires, entièrement offert, et le service
                # de vente lui écrit un règlement « offert » (FREE). Ce parcours n'a pas
                # de clé d'idempotence (pas d'écran de paiement) : la vente n'en a pas.
                # / An ordinary sale with no money: the gift top-up is fully offered,
                #   the service writes a FREE payment. No idempotency key on this path.
                vente_de_la_recharge_cadeau = ouvrir_vente(
                    origine=SaleOrigin.LABOUTIK,
                    nature=Vente.Nature.VENTE,
                    point_de_vente=point_de_vente,
                    operateur=_operateur_de_la_caisse(
                        request, request.POST.get("tag_id_cm", "")
                    ),
                    client=carte.user,
                    carte=carte,
                )
                _executer_recharges(
                    articles_panier,
                    wallet_client,
                    carte,
                    code_methode_paiement="gift",
                    ip_client=ip_client,
                    point_de_vente=point_de_vente,
                    vente=vente_de_la_recharge_cadeau,
                )
                encaisser_vente(vente_de_la_recharge_cadeau)

            # Calculer le solde apres credit pour l'ecran de succes
            # / Compute balance after credit for the success screen
            solde_apres = 0
            try:
                solde_apres = (
                    WalletService.obtenir_total_en_centimes(wallet_client) / 100
                )
            except Exception:
                pass

            # Construire le recapitulatif des articles credites
            # / Build the recap of credited items
            carte_label = carte.tag_id
            if user:
                carte_label = user.first_name or carte.tag_id
            articles_pour_recapitulatif = _construire_recapitulatif_articles(
                articles_panier,
                carte_label,
                "",
            )

            # Construire donnees_paiement minimal pour le template de succes
            # / Build minimal payment data for the success template
            donnees_paiement = {
                "total": total_en_euros * 100,
                "give_back": 0,
                "uuid_transaction": "",
            }
            state = request.POST.get("stateJson", "{}")
            context = {
                "currency_data": CURRENCY_DATA,
                "payment": donnees_paiement,
                "moyen_paiement": _("crédit offert"),
                "total": total_en_euros,
                "state": state,
                "deposit_is_present": False,
                "original_payment": None,
                "uuid_transaction": "",
                "uuid_pv": uuid_pv or "",
                # Infos supplementaires pour l'ecran de succes NFC
                # / Additional info for NFC success screen
                "carte_tag_id": carte.tag_id,
                "solde_apres": solde_apres,
                "articles_pour_recapitulatif": articles_pour_recapitulatif,
            }
            return render(
                request, "laboutik/partial/hx_return_payment_success.html", context
            )

        # User identifie → ecran recapitulatif avec articles et boutons de paiement
        # / User identified → recap screen with articles and payment buttons
        if user:
            solde = 0
            if hasattr(user, "wallet") and user.wallet:
                try:
                    solde = WalletService.obtenir_total_en_centimes(user.wallet) / 100
                except Exception:
                    solde = 0

            user_prenom = user.first_name or prenom
            user_nom = user.last_name or nom

            return _rendre_popup_paiement_client_identifie(
                request,
                point_de_vente=point_de_vente,
                articles_panier=articles_panier,
                total_centimes=total_centimes,
                moyens_paiement_du_post=moyens_paiement,
                client_email=user.email,
                client_prenom=user_prenom,
                client_nom=user_nom,
                client_solde=solde,
                tag_id=tag_id,
                panier_a_recharges=panier_a_recharges,
                panier_a_adhesions=panier_a_adhesions,
                panier_a_billets=panier_a_billets,
            )

        # ------------------------------------------------------------------
        # Carte anonyme (scan NFC, pas de user associe a la carte).
        # Anonymous card (NFC scan, no user linked to the card).
        #
        # QUAND LE FORMULAIRE EMAIL/NOM/PRENOM S'AFFICHE :
        # Le formulaire ne s'affiche que si le panier contient un article
        # qui NECESSITE un user en base de donnees :
        #   - Adhesion (AD) → cree un Membership lie a un user
        #   - Billet → cree une Reservation liee a un user
        #
        # QUAND LE FORMULAIRE NE S'AFFICHE PAS :
        # Si le panier ne contient QUE des recharges (RE/RC/TM), le user
        # n'est pas necessaire. La recharge credite le wallet de la carte
        # (wallet_ephemere pour les cartes anonymes, cree automatiquement).
        # On passe directement au recapitulatif avec les boutons de paiement.
        #
        # WHEN THE EMAIL/NAME FORM IS SHOWN:
        # Only when the cart contains an item that REQUIRES a user in DB:
        #   - Membership (AD) → creates a Membership linked to a user
        #   - Ticket → creates a Reservation linked to a user
        #
        # WHEN THE FORM IS SKIPPED:
        # If the cart contains ONLY top-ups (RE/RC/TM), no user is needed.
        # The top-up credits the card's wallet (wallet_ephemere for anonymous
        # cards, auto-created). We go straight to recap with payment buttons.
        # ------------------------------------------------------------------
        if carte and not user:
            panier_necessite_un_user = panier_a_adhesions or panier_a_billets

            if panier_necessite_un_user:
                # Adhesion ou billet dans le panier → il faut identifier le client
                # / Membership or ticket in cart → client identification required
                context = {
                    "tag_id": tag_id,
                    "panier_a_recharges": panier_a_recharges,
                    "panier_a_adhesions": panier_a_adhesions,
                    "panier_a_billets": panier_a_billets,
                    "moyens_paiement_csv": moyens_paiement_csv,
                }
                return render(
                    request,
                    "laboutik/partial/hx_formulaire_identification_client.html",
                    context,
                )

            # Recharge seule sur carte anonyme → pas besoin de user.
            # On affiche le recapitulatif directement avec le tag_id de la carte.
            # Le wallet_ephemere sera cree automatiquement par _payer_par_recharge()
            # si la carte n'en a pas encore.
            # / Top-up only on anonymous card → no user needed.
            # Show recap directly with the card's tag_id.
            # wallet_ephemere will be auto-created by _payer_par_recharge()
            # if the card doesn't have one yet.
            solde_carte = 0
            if carte.wallet_ephemere:
                try:
                    solde_carte = (
                        WalletService.obtenir_total_en_centimes(carte.wallet_ephemere)
                        / 100
                    )
                except Exception:
                    solde_carte = 0
            elif carte.user and hasattr(carte.user, "wallet") and carte.user.wallet:
                try:
                    solde_carte = (
                        WalletService.obtenir_total_en_centimes(carte.user.wallet) / 100
                    )
                except Exception:
                    solde_carte = 0

            # Le recapitulatif nomme la carte par son tag_id (pas de nom de client).
            # / The recap names the card by its tag_id (no client name).
            return _rendre_popup_paiement_client_identifie(
                request,
                point_de_vente=point_de_vente,
                articles_panier=articles_panier,
                total_centimes=total_centimes,
                moyens_paiement_du_post=moyens_paiement,
                client_email="",
                client_prenom=_("Carte anonyme"),
                client_nom=carte.tag_id,
                client_solde=solde_carte,
                tag_id=tag_id,
                panier_a_recharges=panier_a_recharges,
                panier_a_adhesions=panier_a_adhesions,
                panier_a_billets=panier_a_billets,
            )

        # Aucune info → formulaire vierge
        # / No info → blank form
        context = {
            "panier_a_recharges": panier_a_recharges,
            "panier_a_adhesions": panier_a_adhesions,
            "panier_a_billets": panier_a_billets,
            "moyens_paiement_csv": moyens_paiement_csv,
        }
        return render(
            request,
            "laboutik/partial/hx_formulaire_identification_client.html",
            context,
        )

    # ----------------------------------------------------------------------- #
    #  Annexes : lecture et vérification de carte NFC                           #
    #  Utilities: NFC card reading and checking                                #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["get"], url_path="lire_nfc", url_name="lire_nfc")
    def lire_nfc(self, request):
        """
        GET /laboutik/paiement/lire_nfc/
        Affiche le partial d'attente de lecture NFC (pour paiement cashless).
        Displays the NFC read waiting partial (for cashless payment).
        """
        return render(request, "laboutik/partial/hx_read_nfc.html", {})

    # ----------------------------------------------------------------------- #
    #  Paiement complémentaire NFC (espèces, CB, ou 2ème carte)                #
    #  NFC complement payment (cash, CC, or 2nd card)                          #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["get"],
        url_path="lire_nfc_complement",
        url_name="lire_nfc_complement",
    )
    def lire_nfc_complement(self, request):
        """
        GET /laboutik/paiement/lire_nfc_complement/
        Affiche l'écran d'attente NFC pour la 2ème carte (complément).
        Les données cascade de la carte1 sont propagées via query params.
        / Displays the NFC wait screen for the 2nd card (complement).
        Card1 cascade data is propagated via query params.

        LOCALISATION : laboutik/views.py
        """
        tag_id_carte1 = request.GET.get("tag_id_carte1", "")
        cascade_carte1_json = request.GET.get("cascade_carte1", "[]")
        total_nfc_carte1 = request.GET.get("total_nfc_carte1", "0")

        context = {
            "tag_id_carte1": tag_id_carte1,
            "cascade_carte1_json": cascade_carte1_json,
            "total_nfc_carte1": total_nfc_carte1,
        }
        return render(
            request,
            "laboutik/partial/hx_lire_nfc_complement.html",
            context,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="payer_complementaire",
        url_name="payer_complementaire",
    )
    def payer_complementaire(self, request):
        """
        POST /laboutik/paiement/payer_complementaire/
        Protege le paiement complementaire contre un double envoi, puis l'execute.
        / Guards the complementary payment against a double submit, then runs it.

        LOCALISATION : laboutik/views.py

        Meme cle d'idempotence que payer() : complement-form inclut #addition-form.
        Le 1er passage « 2e carte insuffisante » n'ecrit rien en base : le 2e
        passage peut donc reutiliser la meme cle sans etre pris pour un doublon.
        / Same idempotency key as payer(). The "2nd card insufficient" first pass
        writes nothing, so the second pass can reuse the key.
        """
        return _executer_avec_cle_idempotence(
            request,
            self._executer_paiement_complementaire,
        )

    def _executer_paiement_complementaire(self, request, uuid_transaction_impose=None):
        """
        Finalise un paiement NFC avec complément (espèces, CB, ou 2ème carte).
        / Finalizes an NFC payment with complement (cash, CC, or 2nd card).

        LOCALISATION : laboutik/views.py

        Flux / Flow:
        1. Relire les articles du panier depuis les repid-* du POST
        2. Relire tag_id_carte1, cascade_carte1 (JSON), total_nfc_carte1
        3. Relire moyen_complement (espece, carte_bancaire, ou nfc)
        4. Retrouver la carte1 et son wallet
        5. RE-CALCULER la cascade (protection race condition)
        6. Si espèces ou CB → bloc atomic (débits NFC + lignes espèces/CB)
        7. Si NFC → cascade sur la 2ème carte, si insuffisant → re-render
        8. Succès → render hx_return_payment_success.html
        """

        import json as json_module
        from collections import OrderedDict

        # ---------------------------------------------------------- #
        # 1. Relire le point de vente et les articles du panier
        # / 1. Re-read the POS and cart articles
        # ---------------------------------------------------------- #
        donnees_paiement = request.POST.dict()
        uuid_pv = donnees_paiement.get("uuid_pv")
        try:
            point_de_vente = PointDeVente.objects.get(uuid=uuid_pv)
        except (PointDeVente.DoesNotExist, ValueError):
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": _("Point de vente introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=404
            )

        try:
            articles_panier = _extraire_articles_du_panier(request.POST, point_de_vente)
        except ValueError as e:
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": str(e),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # Un panier en points ou en temps ne se complete jamais : il se paie avec
        # une seule carte (le popup « solde insuffisant » ne propose pas de
        # complement). Cette garde refuse un POST direct.
        # / A points or time cart is never completed: refuses a direct POST.
        if _panier_est_en_points(articles_panier):
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": _(
                    "Un panier en points ou en temps se paie uniquement avec la "
                    "carte du client."
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # Une recharge cadeau se fait à part : même garde que `_executer_paiement`,
        # pour un POST qui arriverait directement ici. Avant tout débit.
        # / A gift top-up is done on its own: same guard as _executer_paiement.
        if _panier_melange_recharge_cadeau_et_autres_articles(articles_panier):
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": _(
                    "La recharge cadeau se fait à part : retirez les autres articles."
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        total_centimes = _calculer_total_panier_centimes(articles_panier)
        state = _construire_state(point_de_vente, user=request.user)

        # ---------------------------------------------------------- #
        # 2. Relire les données cascade de la carte1
        # / 2. Re-read card1 cascade data
        # ---------------------------------------------------------- #
        tag_id_carte1 = request.POST.get("tag_id_carte1", "").upper().strip()
        moyen_complement = request.POST.get("moyen_complement", "")

        # ---------------------------------------------------------- #
        # 3. Retrouver la carte1 et son wallet
        # / 3. Find card1 and its wallet
        # ---------------------------------------------------------- #
        try:
            carte1 = CarteCashless.objects.get(tag_id=tag_id_carte1)
        except CarteCashless.DoesNotExist:
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "warning",
                "msg_content": _("Carte 1 inconnue"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur)

        wallet_carte1 = _obtenir_ou_creer_wallet(carte1)
        tenant_courant = connection.tenant

        # ---------------------------------------------------------- #
        # 4. RE-CALCULER la cascade sur la carte1 (race condition)
        # / 4. RE-CALCULATE cascade on card1 (race condition protection)
        # ---------------------------------------------------------- #
        assets_accessibles = AssetService.obtenir_assets_accessibles(tenant_courant)

        soldes_cascade_carte1 = OrderedDict()
        for categorie_fiduciaire in ORDRE_CASCADE_FIDUCIAIRE:
            asset_pour_categorie = assets_accessibles.filter(
                category=categorie_fiduciaire,
            ).first()
            if asset_pour_categorie is not None:
                solde_asset = WalletService.obtenir_solde(
                    wallet=wallet_carte1, asset=asset_pour_categorie
                )
                if solde_asset > 0:
                    soldes_cascade_carte1[asset_pour_categorie] = solde_asset

        # Classifier les articles (même logique que _payer_par_nfc Phase 2)
        # / Classify articles (same logic as _payer_par_nfc Phase 2)
        articles_fiduciaires = []
        articles_adhesion = []
        articles_recharge_gratuite = []
        articles_non_fiduciaires = []

        for article in articles_panier:
            produit = article["product"]
            prix_obj = article["price"]
            methode = produit.methode_caisse

            # Aucun tarif en points n'arrive ici : la garde en tete de cette
            # fonction refuse un panier en points. Si elle etait retiree, ce
            # classement (adhesion d'abord) debiterait en euros une adhesion en
            # points : reprendre alors celui de _payer_par_nfc (phase 2).
            # / No points price reaches this point (guard at the top). Without
            #   that guard, this order would debit a points membership in euros.
            if produit.categorie_article == Product.ADHESION:
                articles_adhesion.append(article)
            elif methode in METHODES_RECHARGE_GRATUITES:
                articles_recharge_gratuite.append(article)
            elif (
                getattr(prix_obj, "non_fiduciaire", False)
                and prix_obj.asset is not None
            ):
                articles_non_fiduciaires.append(article)
            else:
                articles_fiduciaires.append(article)

        articles_pour_cascade = articles_fiduciaires + articles_adhesion

        # Cascade carte1 (recalcul)
        # / Card1 cascade (recalculation)
        lignes_nfc_carte1 = []
        soldes_restants_c1 = OrderedDict()
        for asset_c, solde_c in soldes_cascade_carte1.items():
            soldes_restants_c1[asset_c] = solde_c

        assets_debites = set()

        for article_cascade in articles_pour_cascade:
            montant_total_article = (
                article_cascade["prix_centimes"] * article_cascade["quantite"]
            )
            reste_article = montant_total_article

            for asset_courant, solde_courant in soldes_restants_c1.items():
                if reste_article <= 0:
                    break
                if solde_courant <= 0:
                    continue

                debit_sur_cet_asset = min(solde_courant, reste_article)
                payment_method_pour_asset = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[
                    asset_courant.category
                ]
                lignes_nfc_carte1.append(
                    (
                        article_cascade,
                        asset_courant,
                        debit_sur_cet_asset,
                        payment_method_pour_asset,
                    )
                )
                soldes_restants_c1[asset_courant] -= debit_sur_cet_asset
                reste_article -= debit_sur_cet_asset
                assets_debites.add(asset_courant)

            if reste_article > 0:
                lignes_nfc_carte1.append((article_cascade, None, reste_article, None))

        # Calculer le total complémentaire restant
        # / Calculate remaining complement total
        total_complementaire = 0
        for _art, asset_ligne, amount_ligne, _pm in lignes_nfc_carte1:
            if asset_ligne is None:
                total_complementaire += amount_ligne

        if total_complementaire <= 0:
            # Race condition heureuse : entre-temps le client a assez
            # → payer normalement (rediriger vers payer avec moyen_paiement=nfc)
            # / Happy race condition: client now has enough → pay normally
            context_erreur = {
                "action": "initUrlAddition();",
                "msg_type": "info",
                "msg_content": _(
                    "Le solde a changé, le paiement complet est possible. Réessayez."
                ),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur)

        # ---------------------------------------------------------- #
        # 5. Aiguillage selon le moyen de complément
        # / 5. Route based on complement method
        # ---------------------------------------------------------- #

        ip_client = request.META.get("REMOTE_ADDR", "0.0.0.0")
        # Cle d'idempotence de payer() si fournie / idempotency key when provided
        uuid_transaction = uuid_transaction_impose or uuid_module.uuid4()

        donnees_paiement["total"] = total_centimes
        donnees_paiement["missing"] = 0
        donnees_paiement["give_back"] = 0

        # Somme donnee en centimes : saisie au pave especes (hx_confirm_payment.html).
        # Vide = compte juste.
        # / Given sum in cents, typed on the cash keypad. Empty = exact amount.
        somme_donnee_brute = donnees_paiement.get("given_sum", "")
        # Le JS envoie « somme x 100 » : ca peut donner 329.99999999999994.
        # On arrondit au centime au lieu d'un int() qui planterait.
        # / JS sends "sum x 100", which may be a float: round to the cent.
        donnees_paiement["given_sum"] = 0
        if somme_donnee_brute != "" and moyen_complement == "espece":
            try:
                donnees_paiement["given_sum"] = round(float(somme_donnee_brute))
            except ValueError:
                donnees_paiement["given_sum"] = 0

        # Reste apres une 2e carte, regle en especes ou en CB.
        # L'ecran « reste a payer » du 2e passage (2e carte insuffisante) renvoie
        # tag_id_carte2. On repart alors dans la branche 2e carte : elle recalcule
        # et debite les DEUX cartes, puis regle le reste avec le moyen choisi.
        # Sans ce routage, la branche especes/CB ne voyait que la carte 1 :
        # le reste attendu etait faux (especes refusees) et la carte 2 n'etait
        # jamais debitee (CB).
        # / Remainder after a 2nd card, paid in cash or CC: route to the 2nd-card
        #   branch, which debits BOTH cards, then settles the rest with this method.
        tag_id_carte2_du_complement = (
            request.POST.get("tag_id_carte2", "").upper().strip()
        )
        moyen_reste_apres_carte2 = ""
        reste_apres_carte2_en_especes_ou_cb = (
            moyen_complement in ("espece", "carte_bancaire")
            and tag_id_carte2_du_complement != ""
        )
        if reste_apres_carte2_en_especes_ou_cb:
            moyen_reste_apres_carte2 = moyen_complement
            moyen_complement = "nfc"

        if moyen_complement in ("espece", "carte_bancaire"):
            # ---------------------------------------------------------- #
            # 6. Complément espèces ou CB
            # / 6. Cash or CC complement
            # ---------------------------------------------------------- #
            # Déterminer le PaymentMethod pour le complément
            # / Determine PaymentMethod for the complement
            if moyen_complement == "espece":
                pm_complement = PaymentMethod.CASH
            else:
                pm_complement = PaymentMethod.CC

            # ===== CRAN LEGACY (C2.3) : le FED couvre une partie du reste, le solde en espèces/CB =====
            # On re-lit le FED FRAIS (anti-race), il couvre ce qu'il peut du reste. Débit HORS atomic
            # (appel réseau). Échec → fail-fast : rescan (aucun débit local). Le solde restant sera
            # réglé par le moyen complémentaire choisi (espèces/CB).
            # / LEGACY tier (C2.3): fresh FED read; cover what it can; debit OUTSIDE atomic; the
            # remaining balance is settled by the chosen complement method (cash/CC).
            lignes_legacy = []
            transactions_legacy = []
            montant_legacy = 0
            lignes_locales_c1 = [t for t in lignes_nfc_carte1 if t[1] is not None]
            lignes_complement_c1 = [t for t in lignes_nfc_carte1 if t[1] is None]
            if carte1.user is not None and lignes_complement_c1:
                depensable_legacy, legacy_disponible = lire_depensable_fed_frais(carte1.user)
                if legacy_disponible and depensable_legacy > 0:
                    montant_legacy = min(depensable_legacy, total_complementaire)

            # Montant reellement regle en especes/CB : le reste moins la part legacy.
            # / Amount actually settled in cash/CC: remainder minus the legacy part.
            montant_paye_en_complement = total_complementaire - montant_legacy

            # Especes : la somme donnee doit couvrir ce montant (0 = compte juste).
            # On verifie AVANT le debit legacy : rien n'est debite si on refuse.
            # / Cash: the given sum must cover it (0 = exact). Checked BEFORE the legacy debit.
            somme_donnee_en_centimes = donnees_paiement["given_sum"]
            somme_donnee_insuffisante = (
                moyen_complement == "espece"
                and somme_donnee_en_centimes > 0
                and somme_donnee_en_centimes < montant_paye_en_complement
            )
            if somme_donnee_insuffisante:
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _("Somme donnée insuffisante"),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request,
                    "laboutik/partial/hx_messages.html",
                    context_erreur,
                    status=400,
                )

            if montant_legacy > 0:
                lignes_pour_fed, lignes_reste = _decouper_lignes_complement(
                    lignes_complement_c1, montant_legacy
                )
                try:
                    transactions_legacy = _debiter_legacy(
                        carte1.user, montant_legacy, uuid_transaction
                    )
                except Exception as erreur_legacy:
                    logger.warning(f"Débit legacy (complément) échoué : {erreur_legacy}")
                    context_erreur = {
                        "action": "initUrlAddition();",
                        "msg_type": "warning",
                        "msg_content": _("Le solde du réseau a changé, rescannez la carte"),
                        "selector_bt_retour": "#messages",
                    }
                    return render(
                        request,
                        "laboutik/partial/hx_messages.html",
                        context_erreur,
                        status=409,
                    )
                lignes_legacy = _repartir_legacy_sur_articles(
                    lignes_pour_fed, transactions_legacy
                )
                # Les parts complément couvertes par le FED sont retirées : il ne reste que les
                # locaux + la part à régler en espèces/CB (lignes_reste).
                # / FED-covered parts removed: only locals + cash/CC part (lignes_reste) remain.
                lignes_nfc_carte1 = lignes_locales_c1 + lignes_reste

            # Le journal d'incident du débit legacy, préparé ici, AVANT le bloc atomic :
            # le débit du réseau est déjà fait et ne s'annule pas. Si le bloc échoue ensuite
            # (solde local insuffisant, égalité de la vente rompue, autre erreur), l'argent
            # est prélevé sur le réseau sans vente ni ligne : ce message permet de le
            # régulariser à la main (montant, carte, uuid de chaque transaction du réseau).
            # / The legacy-debit incident log, prepared BEFORE the atomic block: if the block
            #   fails, the network money is taken without a sale; this message allows a
            #   manual fix (amount, card, uuid of each network transaction).
            uuids_des_transactions_legacy = []
            for transaction_legacy in transactions_legacy:
                uuids_des_transactions_legacy.append(str(transaction_legacy[3]))
            message_d_incident_legacy = ""
            if lignes_legacy:
                message_d_incident_legacy = (
                    f"INCIDENT legacy débité sans LigneArticle (complément, atomic échoué) — "
                    f"uuid_transaction={uuid_transaction} carte={carte1.tag_id} "
                    f"montant_legacy={montant_legacy} "
                    f"transactions_legacy={', '.join(uuids_des_transactions_legacy)} : "
                    f"régularisation manuelle requise."
                )

            try:
                with db_transaction.atomic():
                    # 6.0) Ouvrir la vente du paiement
                    # Une seule vente pour tout le paiement : ce que paie la carte 1, ce
                    # que paie le réseau, et le reste en espèces ou en CB. La clé
                    # d'idempotence est l'identifiant du paiement, le même que sur les
                    # lignes : un rejeu retrouve cette vente. Un panier en points n'arrive
                    # jamais ici (garde en tête de fonction) : la vente est en euros.
                    # Le client est le titulaire de la carte 1.
                    # / 6.0) Open the payment's sale: one sale for the whole payment. The
                    #   payment id is its idempotency key. Always in euros.
                    vente = ouvrir_vente(
                        origine=SaleOrigin.LABOUTIK,
                        nature=Vente.Nature.VENTE,
                        point_de_vente=point_de_vente,
                        operateur=_operateur_de_la_caisse(
                            request, request.POST.get("tag_id_cm", "")
                        ),
                        client=carte1.user,
                        carte=carte1,
                        idempotency_key=str(uuid_transaction),
                    )

                    # 6a) Recharges gratuites
                    # Elles n'arrivent pas ici aujourd'hui : une recharge cadeau mêlée à
                    # d'autres articles est refusée plus haut, et seule elle ne laisse
                    # rien à payer (sortie « le solde a changé »). Si une garde change,
                    # elles restent des articles de la MÊME vente, avec l'identifiant du
                    # paiement sur leurs lignes.
                    # / 6a) Free top-ups: unreachable today (guards above). If a guard
                    #   changes, they stay items of the SAME sale, with the payment id.
                    if articles_recharge_gratuite:
                        _executer_recharges(
                            articles_recharge_gratuite,
                            wallet_carte1,
                            carte1,
                            code_methode_paiement="gift",
                            ip_client=ip_client,
                            point_de_vente=point_de_vente,
                            vente=vente,
                            uuid_transaction=uuid_transaction,
                        )

                    # 6b) Débits non-fiduciaires
                    # Une transaction par article, et un règlement par transaction : son
                    # montant et son uuid sont COPIÉS de la transaction renvoyée.
                    # / 6b) Non-fiduciary debits: one payment per transaction, copied
                    #   from the returned transaction.
                    lignes_non_fidu = []
                    for article_nf in articles_non_fiduciaires:
                        asset_nf_cible = article_nf["price"].asset
                        montant_nf = (
                            article_nf["prix_centimes"] * article_nf["quantite"]
                        )
                        transaction_non_fiduciaire = TransactionService.creer_vente(
                            sender_wallet=wallet_carte1,
                            receiver_wallet=asset_nf_cible.wallet_origin,
                            asset=asset_nf_cible,
                            montant_en_centimes=montant_nf,
                            tenant=tenant_courant,
                            card=carte1,
                            ip=ip_client,
                        )
                        pm_nf = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[
                            asset_nf_cible.category
                        ]
                        ajouter_reglement(
                            vente,
                            moyen=pm_nf,
                            montant=transaction_non_fiduciaire.amount,
                            asset=asset_nf_cible.uuid,
                            carte=carte1,
                            wallet=wallet_carte1,
                            fedow_transaction_uuid=transaction_non_fiduciaire.uuid,
                        )
                        lignes_non_fidu.append(
                            (article_nf, asset_nf_cible, montant_nf, pm_nf)
                        )
                        assets_debites.add(asset_nf_cible)

                    # 6c) Débits fiduciaires cascade carte1
                    # / 6c) Card1 fiduciary cascade debits
                    debits_par_asset_c1 = OrderedDict()
                    for _art_c, asset_c, amount_c, _pm_c in lignes_nfc_carte1:
                        if asset_c is not None:
                            if asset_c not in debits_par_asset_c1:
                                debits_par_asset_c1[asset_c] = 0
                            debits_par_asset_c1[asset_c] += amount_c

                    # Un règlement par transaction : son montant et son uuid sont COPIÉS
                    # de la transaction renvoyée, jamais recalculés depuis les parts.
                    # Jetons cadeau : règlement « jetons » (LG), un vrai règlement
                    # (D8 bis).
                    # / One payment per transaction, copied from it. Gift tokens: LG.
                    for (
                        asset_a_debiter,
                        total_debit_asset,
                    ) in debits_par_asset_c1.items():
                        transaction_de_la_monnaie = TransactionService.creer_vente(
                            sender_wallet=wallet_carte1,
                            receiver_wallet=asset_a_debiter.wallet_origin,
                            asset=asset_a_debiter,
                            montant_en_centimes=total_debit_asset,
                            tenant=tenant_courant,
                            card=carte1,
                            ip=ip_client,
                        )
                        ajouter_reglement(
                            vente,
                            moyen=MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[
                                asset_a_debiter.category
                            ],
                            montant=transaction_de_la_monnaie.amount,
                            asset=asset_a_debiter.uuid,
                            carte=carte1,
                            wallet=wallet_carte1,
                            fedow_transaction_uuid=transaction_de_la_monnaie.uuid,
                        )

                    # 6c bis) Règlements du débit legacy (fait plus haut, hors atomic)
                    # Un règlement par transaction du réseau, lu dans `transactions_legacy`
                    # et non dans les parts (une part a perdu le lien avec sa
                    # transaction). La transaction vit sur le serveur Fedow distant : son
                    # uuid va dans `reference_externe` (`fedow_transaction_uuid` est
                    # réservé aux transactions `fedow_core` locales).
                    # / One payment per network transaction, read from transactions_legacy.
                    #   Remote transaction: its uuid goes to reference_externe.
                    for transaction_legacy in transactions_legacy:
                        asset_legacy_uuid = transaction_legacy[0]
                        montant_legacy_de_la_transaction = transaction_legacy[1]
                        moyen_legacy = transaction_legacy[2]
                        uuid_de_la_transaction_legacy = transaction_legacy[3]
                        ajouter_reglement(
                            vente,
                            moyen=moyen_legacy,
                            montant=montant_legacy_de_la_transaction,
                            asset=asset_legacy_uuid,
                            carte=carte1,
                            reference_externe=str(uuid_de_la_transaction_legacy),
                        )

                    # 6c ter) Règlement du reste, en espèces ou en CB
                    # UN règlement du reste dû (le reste après la carte et le réseau),
                    # jamais la somme donnée par le client : la monnaie rendue n'est pas
                    # un règlement. Pas de règlement de 0 (réseau qui paie tout le reste).
                    # / ONE payment of the amount due, never the amount handed over: the
                    #   change given back is not a payment. No 0 payment.
                    if montant_paye_en_complement > 0:
                        ajouter_reglement(
                            vente,
                            moyen=pm_complement,
                            montant=montant_paye_en_complement,
                        )

                    # 6d) Remplacer les lignes complémentaires (asset=None)
                    # par des lignes espèces/CB
                    # / 6d) Replace complement lines (asset=None) with cash/CC lines
                    lignes_finales = []
                    for art_c, asset_c, amount_c, pm_c in lignes_nfc_carte1:
                        if asset_c is None:
                            # Ligne complémentaire → espèces ou CB
                            # / Complement line → cash or CC
                            lignes_finales.append(
                                (art_c, None, amount_c, pm_complement)
                            )
                        else:
                            lignes_finales.append((art_c, asset_c, amount_c, pm_c))

                    # + lignes_legacy : parts couvertes par le FED (débit déjà fait hors atomic),
                    # avec leur moyen résolu (STRIPE_FED / LOCAL_EURO) et l'uuid de l'asset distant.
                    # / + lignes_legacy: FED-covered parts (already debited outside atomic).
                    toutes_les_lignes = lignes_non_fidu + lignes_finales + lignes_legacy
                    # Chaque part est un article de la vente.
                    # / Each part is an item of the sale.
                    lignes_creees, produits_stock_negatif = (
                        _creer_lignes_articles_cascade(
                            lignes_pre_calculees=toutes_les_lignes,
                            carte=carte1,
                            wallet=wallet_carte1,
                            uuid_transaction=uuid_transaction,
                            point_de_vente=point_de_vente,
                            vente=vente,
                        )
                    )

                    # 6e) Adhésions
                    # / 6e) Memberships
                    if articles_adhesion:
                        lignes_par_product = {}
                        for ligne_creee in lignes_creees:
                            product_uuid_str = str(
                                ligne_creee.pricesold.productsold.product.uuid
                            )
                            if product_uuid_str not in lignes_par_product:
                                lignes_par_product[product_uuid_str] = ligne_creee

                        for article_ad in articles_adhesion:
                            membership = _creer_ou_renouveler_adhesion(
                                carte1.user,
                                article_ad["product"],
                                article_ad["price"],
                            )
                            if membership:
                                product_uuid_ad = str(article_ad["product"].uuid)
                                ligne_ad = lignes_par_product.get(product_uuid_ad)
                                if ligne_ad:
                                    ligne_ad.membership = membership
                                    ligne_ad.save(update_fields=["membership"])
                                _appliquer_les_effets_d_une_adhesion_vendue_en_caisse(
                                    membership, ligne_ad
                                )

                    # 6f) Encaisser la vente, EN DERNIER
                    # `encaisser_vente` vérifie les deux égalités et pose le numéro. Si
                    # elles ne tiennent pas, il lève `EgaliteDeVenteRompue` : tout le bloc
                    # est annulé (lignes, débits locaux, adhésions).
                    # / 6f) Settle the sale, LAST: a broken equality rolls back the block.
                    encaisser_vente(vente)

            except SoldeInsuffisant:
                # INCIDENT rarissime : si le legacy a déjà été débité (hors atomic) et que l'atomic
                # local échoue, le FED/TLF fédéré est prélevé SANS LigneArticle → on JOURNALISE pour
                # régularisation manuelle (le legacy n'est pas annulable automatiquement).
                # / Rare INCIDENT: legacy debited but local atomic failed → log for manual fix.
                if message_d_incident_legacy:
                    logger.error(message_d_incident_legacy)
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _(
                        "Solde insuffisant. Le solde a changé depuis la lecture."
                    ),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request, "laboutik/partial/hx_messages.html", context_erreur
                )

            # Cet `except` vient AVANT `except Exception` : sinon l'égalité rompue
            # partirait en erreur 500.
            # / This `except` comes BEFORE `except Exception`: otherwise a 500.
            except EgaliteDeVenteRompue as erreur_d_egalite:
                # Les règlements ne couvrent pas exactement les articles : le bloc atomic
                # a tout annulé (lignes, débits locaux, adhésions). Le débit legacy, fait
                # avant, reste : même journal d'incident que pour un solde insuffisant.
                # La caisse montre son écran d'erreur, jamais une erreur 500.
                # / Broken equality: the atomic block rolled everything back. The legacy
                #   debit stays: same incident log. The register shows its error screen.
                if message_d_incident_legacy:
                    logger.error(message_d_incident_legacy)
                logger.error(
                    f"Vente complément refusée (égalité rompue) — "
                    f"uuid_transaction={uuid_transaction} carte={carte1.tag_id} : "
                    f"{erreur_d_egalite}"
                )
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _(
                        "Le paiement n'a pas été enregistré : la vente est incohérente. "
                        "Prévenez un responsable du lieu."
                    ),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request,
                    "laboutik/partial/hx_messages.html",
                    context_erreur,
                    status=409,
                )

            except Exception as e:
                # Toute AUTRE exception dans l'atomic : si le legacy a deja ete debite
                # (hors atomic), le local rollback mais le FED/TLF federe reste preleve
                # SANS LigneArticle (orphelin). On JOURNALISE l'incident, avec les uuid
                # des transactions du reseau, puis on relaie l'exception (500 volontaire).
                # Pas de journalisation en base, juste le log.
                # / Any OTHER exception in the atomic: if the legacy debit already happened
                # (outside the atomic), the local rolls back but the federated FED/TLF stays
                # debited WITHOUT LigneArticle (orphan). Log the incident (with the network
                # transaction uuids) then re-raise (500).
                if lignes_legacy:
                    logger.error(
                        f"INCIDENT : débit legacy orphelin (complément, exception atomic) — "
                        f"carte={carte1.tag_id} montant_legacy_centimes={montant_legacy} "
                        f"transactions_legacy={', '.join(uuids_des_transactions_legacy)} "
                        f"uuid_transaction={uuid_transaction} exception={e}"
                    )
                raise

            # ---------------------------------------------------------- #
            # Succès espèces/CB → affichage
            # / Cash/CC success → display
            # ---------------------------------------------------------- #
            # Avant / apres de la carte : non-fiduciaires + cascade locale
            # / Card before / after: non-fiduciary + local cascade
            soldes_apres_paiement = _calculer_soldes_apres_paiement(
                wallet=wallet_carte1,
                lignes_debitees=lignes_non_fidu + lignes_nfc_carte1,
            )

            # Regroupement par carte pour l'ecran de succes (un cadre par carte)
            # / Grouped per card for the success screen (one frame per card)
            cartes_apres_paiement = []
            if soldes_apres_paiement:
                cartes_apres_paiement.append(
                    {"tag_id": carte1.tag_id, "soldes": soldes_apres_paiement}
                )

            nouveau_solde_euros = None
            nom_monnaie_principal = ""
            if soldes_apres_paiement:
                nouveau_solde_euros = soldes_apres_paiement[0]["solde_euros"]
                nom_monnaie_principal = soldes_apres_paiement[0]["name"]

            # Monnaie a rendre (en euros), meme regle que payer()
            # / Change to give back (euros), same rule as payer()
            if (
                moyen_complement == "espece"
                and somme_donnee_en_centimes > montant_paye_en_complement
            ):
                donnees_paiement["give_back"] = (
                    somme_donnee_en_centimes - montant_paye_en_complement
                ) / 100

            context_succes = {
                "currency_data": CURRENCY_DATA,
                "payment": donnees_paiement,
                "monnaie_name": nom_monnaie_principal,
                "moyen_paiement": moyen_complement,
                "original_payment": True,
                "original_moyen_paiement": _("NFC"),
                "deposit_is_present": False,
                "total": total_centimes / 100,
                "state": state,
                "nouveau_solde": nouveau_solde_euros,
                "card_name": carte1.tag_id,
                "uuid_transaction": str(uuid_transaction),
                "uuid_vente": _uuid_de_la_vente_du_paiement(uuid_transaction),
                "uuid_pv": str(point_de_vente.uuid),
                "soldes_apres_paiement": soldes_apres_paiement,
                "cartes_apres_paiement": cartes_apres_paiement,
                "produits_stock_negatif": produits_stock_negatif,
            }
            return render(
                request,
                "laboutik/partial/hx_return_payment_success.html",
                context_succes,
            )

        elif moyen_complement == "nfc":
            # ---------------------------------------------------------- #
            # 7. Complément 2ème carte NFC
            # / 7. 2nd NFC card complement
            # ---------------------------------------------------------- #
            # Carte 2 : lue au NFC (1er passage), ou renvoyee par l'ecran
            # « reste a payer » quand on regle le reste en especes / CB.
            # / Card 2: read via NFC, or sent back by the remainder screen.
            if moyen_reste_apres_carte2:
                tag_id_carte2 = tag_id_carte2_du_complement
            else:
                tag_id_carte2 = request.POST.get("tag_id", "").upper().strip()

            if not tag_id_carte2:
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _("Carte non lue"),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request, "laboutik/partial/hx_messages.html", context_erreur
                )

            # Vérifier que la 2ème carte != la 1ère
            # / Check 2nd card != 1st card
            if tag_id_carte2 == tag_id_carte1:
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _(
                        "La 2ème carte est la même que la 1ère. "
                        "Utilisez une carte différente."
                    ),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request, "laboutik/partial/hx_messages.html", context_erreur
                )

            try:
                carte2 = CarteCashless.objects.get(tag_id=tag_id_carte2)
            except CarteCashless.DoesNotExist:
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _("Carte 2 inconnue"),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request, "laboutik/partial/hx_messages.html", context_erreur
                )

            wallet_carte2 = _obtenir_ou_creer_wallet(carte2)

            # ===== CRAN LEGACY (C2.5) : le FED de carte1 reporté AVANT la cascade carte2 =====
            # La branche espèces/CB ré-applique le FED legacy de carte1 ; cette branche NFC
            # l'oubliait (bug C). On le reporte ici, AVANT la cascade de carte2, pour que le
            # reste à payer soit juste. CALCUL SEUL : on réduit les lignes complément de carte1,
            # mais le DÉBIT du FED est DIFFÉRÉ au bloc atomic (succès uniquement) — sinon le
            # re-render « insuffisant » débiterait le FED sans créer de ligne (orphelin).
            # / LEGACY tier (C2.5): carry over card1's legacy FED BEFORE card2's cascade so the
            # remaining amount is correct. CALCULATION ONLY: the FED debit is DEFERRED to the
            # success atomic (a re-render would otherwise orphan the debit).
            lignes_legacy_c1 = []
            transactions_legacy_c1 = []
            lignes_pour_fed_c1 = []
            montant_legacy_c1 = 0
            lignes_complement_c1 = [t for t in lignes_nfc_carte1 if t[1] is None]
            lignes_locales_c1 = [t for t in lignes_nfc_carte1 if t[1] is not None]
            total_complement_c1 = sum(
                amount for _a, _u, amount, _p in lignes_complement_c1
            )
            if carte1.user is not None and total_complement_c1 > 0:
                depensable_legacy_c1, dispo_c1 = lire_depensable_fed_frais(carte1.user)
                if dispo_c1 and depensable_legacy_c1 > 0:
                    montant_legacy_c1 = min(depensable_legacy_c1, total_complement_c1)
            if montant_legacy_c1 > 0:
                # On découpe le complément de carte1 : la part couverte par son FED (différée)
                # et le reste, que la carte2 (puis espèces/CB) devra couvrir.
                # / Split card1's complement: the FED-covered part (deferred) and the rest.
                lignes_pour_fed_c1, lignes_reste_c1 = _decouper_lignes_complement(
                    lignes_complement_c1, montant_legacy_c1
                )
                lignes_nfc_carte1 = lignes_locales_c1 + lignes_reste_c1

            # Cascade sur la 2ème carte pour le reste
            # / Cascade on 2nd card for the remainder
            soldes_cascade_carte2 = OrderedDict()
            for categorie_fiduciaire in ORDRE_CASCADE_FIDUCIAIRE:
                asset_pour_categorie = assets_accessibles.filter(
                    category=categorie_fiduciaire,
                ).first()
                if asset_pour_categorie is not None:
                    solde_asset = WalletService.obtenir_solde(
                        wallet=wallet_carte2, asset=asset_pour_categorie
                    )
                    if solde_asset > 0:
                        soldes_cascade_carte2[asset_pour_categorie] = solde_asset

            # Construire les lignes carte2 à partir des lignes complémentaires carte1
            # / Build card2 lines from card1 complement lines
            lignes_nfc_carte2 = []
            soldes_restants_c2 = OrderedDict()
            for asset_c, solde_c in soldes_cascade_carte2.items():
                soldes_restants_c2[asset_c] = solde_c

            assets_debites_carte2 = set()
            total_reste_apres_carte2 = 0

            for art_c, asset_c, amount_c, pm_c in lignes_nfc_carte1:
                if asset_c is not None:
                    # Ligne carte1 → déjà couverte, garder telle quelle
                    # / Card1 line → already covered, keep as-is
                    continue

                # Ligne complémentaire → essayer la cascade carte2
                # / Complement line → try card2 cascade
                reste_complement = amount_c
                for asset_c2, solde_c2 in soldes_restants_c2.items():
                    if reste_complement <= 0:
                        break
                    if solde_c2 <= 0:
                        continue

                    debit_c2 = min(solde_c2, reste_complement)
                    pm_c2 = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[
                        asset_c2.category
                    ]
                    lignes_nfc_carte2.append((art_c, asset_c2, debit_c2, pm_c2))
                    soldes_restants_c2[asset_c2] -= debit_c2
                    reste_complement -= debit_c2
                    assets_debites_carte2.add(asset_c2)

                if reste_complement > 0:
                    total_reste_apres_carte2 += reste_complement
                    lignes_nfc_carte2.append((art_c, None, reste_complement, None))

            # ===== CRAN LEGACY (C3) : la 2ème carte du réseau couvre le reste avec son FED =====
            # Si la cascade LOCALE de la carte2 ne suffit pas et que la carte2 est liée à un user,
            # on tente son dépensable fédéré (FED réseau). TOUT-OU-RIEN : on ne débite le legacy que
            # s'il couvre TOUT le reste — sinon le re-render « insuffisant » jetterait la carte2 et le
            # débit serait perdu. Le solde non couvert part en espèces/CB au tour suivant (FED intact).
            # / LEGACY tier (C3): the 2nd networked card covers the remainder with its FED. ALL-OR-
            # NOTHING (a partial debit would be lost by the re-render). Otherwise cash/CC next round.
            lignes_legacy_c2 = []
            transactions_legacy_c2 = []
            montant_legacy_c2 = 0
            if carte2.user is not None and total_reste_apres_carte2 > 0:
                depensable_legacy_c2, legacy_dispo_c2 = lire_depensable_fed_frais(
                    carte2.user
                )
                if legacy_dispo_c2 and depensable_legacy_c2 >= total_reste_apres_carte2:
                    montant_legacy_c2 = total_reste_apres_carte2
            if montant_legacy_c2 > 0:
                # Les lignes complément (asset=None) de la carte2 sont entièrement couvertes par le FED.
                # / The card2 complement lines (asset=None) are fully covered by FED.
                lignes_complement_c2 = [t for t in lignes_nfc_carte2 if t[1] is None]
                lignes_couvertes_locales_c2 = [
                    t for t in lignes_nfc_carte2 if t[1] is not None
                ]
                lignes_pour_fed_c2, lignes_reste_c2 = _decouper_lignes_complement(
                    lignes_complement_c2, montant_legacy_c2
                )
                try:
                    transactions_legacy_c2 = _debiter_legacy(
                        carte2.user, montant_legacy_c2, uuid_transaction
                    )
                except Exception as erreur_legacy_c2:
                    logger.warning(
                        f"Débit legacy (2ème carte) échoué : {erreur_legacy_c2}"
                    )
                    context_erreur = {
                        "action": "initUrlAddition();",
                        "msg_type": "warning",
                        "msg_content": _(
                            "Le solde du réseau a changé, rescannez la carte"
                        ),
                        "selector_bt_retour": "#messages",
                    }
                    return render(
                        request,
                        "laboutik/partial/hx_messages.html",
                        context_erreur,
                        status=409,
                    )
                lignes_legacy_c2 = _repartir_legacy_sur_articles(
                    lignes_pour_fed_c2, transactions_legacy_c2
                )
                # Le FED a couvert tout le reste : plus aucune ligne complément sur la carte2.
                # / FED covered the whole remainder: no complement line left on card2.
                lignes_nfc_carte2 = lignes_couvertes_locales_c2 + lignes_reste_c2
                total_reste_apres_carte2 = 0

            if total_reste_apres_carte2 > 0 and not moyen_reste_apres_carte2:
                # Encore insuffisant → re-render complémentaire sans bouton 2ème carte
                # / Still insufficient → re-render complement without 2nd card button
                debits_affichage_c1 = OrderedDict()
                for _art, asset_l, amount_l, _pm in lignes_nfc_carte1:
                    if asset_l is not None:
                        if asset_l not in debits_affichage_c1:
                            debits_affichage_c1[asset_l] = 0
                        debits_affichage_c1[asset_l] += amount_l

                debits_affichage_c2 = OrderedDict()
                for _art, asset_l, amount_l, _pm in lignes_nfc_carte2:
                    if asset_l is not None:
                        if asset_l not in debits_affichage_c2:
                            debits_affichage_c2[asset_l] = 0
                        debits_affichage_c2[asset_l] += amount_l

                detail_cascade_affichage = []
                for asset_d, montant_d in debits_affichage_c1.items():
                    detail_cascade_affichage.append(
                        {
                            "name": f"{asset_d.name} ({tag_id_carte1})",
                            "montant_euros": f"{montant_d / 100:.2f}",
                        }
                    )
                for asset_d, montant_d in debits_affichage_c2.items():
                    detail_cascade_affichage.append(
                        {
                            "name": f"{asset_d.name} ({tag_id_carte2})",
                            "montant_euros": f"{montant_d / 100:.2f}",
                        }
                    )

                # Resérialiser cascade carte1 pour le re-render
                # / Re-serialize card1 cascade for re-render
                cascade_json_rerender = json_module.dumps(
                    [
                        [str(asset.uuid), montant]
                        for asset, montant in debits_affichage_c1.items()
                    ]
                )

                total_nfc_carte1_centimes = sum(debits_affichage_c1.values())
                total_nfc_carte2_centimes = sum(debits_affichage_c2.values())
                context_complement = {
                    "action": "initUrlAddition();",
                    "tag_id_carte1": tag_id_carte1,
                    # Carte 2 : affichee dans l'addition, et renvoyee par le
                    # formulaire pour regler le reste en especes / CB.
                    # / Card 2: shown in the bill, and sent back by the form.
                    "tag_id_carte2": tag_id_carte2,
                    "total_nfc_carte2_euros": f"{total_nfc_carte2_centimes / 100:.2f}",
                    "detail_cascade": detail_cascade_affichage,
                    "cascade_carte1_json": cascade_json_rerender,
                    "total_nfc_carte1": total_nfc_carte1_centimes,
                    "total_nfc_carte1_euros": f"{total_nfc_carte1_centimes / 100:.2f}",
                    "total_panier_euros": f"{total_centimes / 100:.2f}",
                    "reste_euros": f"{total_reste_apres_carte2 / 100:.2f}",
                    "accepte_especes": point_de_vente.accepte_especes,
                    "accepte_carte_bancaire": point_de_vente.accepte_carte_bancaire,
                    "autoriser_2eme_carte": False,
                }
                return render(
                    request,
                    "laboutik/partial/hx_complement_paiement.html",
                    context_complement,
                )

            # Reste apres la carte 2, regle en especes / CB.
            # Les parts non couvertes (asset=None) deviennent des lignes especes / CB.
            # Controle de la somme donnee AVANT tout debit (legacy carte1 compris).
            # / Remainder after card 2, paid in cash / CC. Given-sum check BEFORE any debit.
            lignes_reste_apres_carte2 = []
            if total_reste_apres_carte2 > 0:
                if moyen_reste_apres_carte2 == "espece":
                    pm_reste = PaymentMethod.CASH
                else:
                    pm_reste = PaymentMethod.CC

                somme_donnee_en_centimes = donnees_paiement["given_sum"]
                somme_donnee_insuffisante = (
                    moyen_reste_apres_carte2 == "espece"
                    and somme_donnee_en_centimes > 0
                    and somme_donnee_en_centimes < total_reste_apres_carte2
                )
                if somme_donnee_insuffisante:
                    context_erreur = {
                        "action": "initUrlAddition();",
                        "msg_type": "warning",
                        "msg_content": _("Somme donnée insuffisante"),
                        "selector_bt_retour": "#messages",
                    }
                    return render(
                        request,
                        "laboutik/partial/hx_messages.html",
                        context_erreur,
                        status=400,
                    )

                for art_r, asset_r, amount_r, _pm_r in lignes_nfc_carte2:
                    if asset_r is None:
                        lignes_reste_apres_carte2.append(
                            (art_r, None, amount_r, pm_reste)
                        )

                # Monnaie a rendre (en euros), meme regle que payer()
                # / Change to give back (euros), same rule as payer()
                if (
                    moyen_reste_apres_carte2 == "espece"
                    and somme_donnee_en_centimes > total_reste_apres_carte2
                ):
                    donnees_paiement["give_back"] = (
                        somme_donnee_en_centimes - total_reste_apres_carte2
                    ) / 100

            # Carte2 couvre tout le reste (ou le reste est regle en especes / CB) → on finalise.
            # Débit DIFFÉRÉ du FED legacy de carte1 (calculé plus haut) : on ne le débite
            # que maintenant, une fois sûr que le paiement se finalise. Hors atomic (appel
            # réseau), fail-fast : si le solde réseau a changé, on rescanne, aucun débit local.
            # / Card1's deferred legacy FED debit (network call, fail-fast), only now that the
            # payment completes.
            if montant_legacy_c1 > 0:
                try:
                    transactions_legacy_c1 = _debiter_legacy(
                        carte1.user, montant_legacy_c1, uuid_transaction
                    )
                except Exception as erreur_legacy_c1:
                    logger.warning(
                        f"Débit legacy (carte1, complément NFC) échoué : {erreur_legacy_c1}"
                    )
                    # Le réseau de la carte 2 est débité plus haut, et ce débit ne
                    # s'annule pas : l'argent de la carte 2 est pris sans vente ni
                    # ligne. On le journalise pour une régularisation à la main
                    # (montant, carte 2, uuid de chaque transaction du réseau).
                    # / Card 2's network debit (above) cannot be undone: its money is
                    #   taken without a sale. Logged for a manual fix.
                    if transactions_legacy_c2:
                        uuids_des_transactions_legacy_c2 = []
                        for transaction_legacy_c2 in transactions_legacy_c2:
                            uuids_des_transactions_legacy_c2.append(
                                str(transaction_legacy_c2[3])
                            )
                        logger.error(
                            f"INCIDENT legacy débité sans LigneArticle (2ème carte, "
                            f"débit legacy de la carte 1 échoué) — "
                            f"uuid_transaction={uuid_transaction} "
                            f"carte2={carte2.tag_id} "
                            f"montant_legacy={montant_legacy_c2} "
                            f"transactions_legacy="
                            f"{', '.join(uuids_des_transactions_legacy_c2)} : "
                            f"régularisation manuelle requise."
                        )
                    context_erreur = {
                        "action": "initUrlAddition();",
                        "msg_type": "warning",
                        "msg_content": _(
                            "Le solde du réseau a changé, rescannez la carte"
                        ),
                        "selector_bt_retour": "#messages",
                    }
                    return render(
                        request,
                        "laboutik/partial/hx_messages.html",
                        context_erreur,
                        status=409,
                    )
                lignes_legacy_c1 = _repartir_legacy_sur_articles(
                    lignes_pour_fed_c1, transactions_legacy_c1
                )

            # Le journal d'incident des débits legacy, préparé ici, AVANT le bloc
            # atomic : les débits du réseau des DEUX cartes sont déjà faits et ne
            # s'annulent pas. Si le bloc échoue ensuite (solde local insuffisant,
            # égalité de la vente rompue), l'argent est prélevé sur le réseau sans
            # vente ni ligne : ce message unique permet de le régulariser à la main
            # (pour chaque carte débitée : la carte, le montant, l'uuid de chaque
            # transaction du réseau).
            # / The legacy-debit incident log, prepared BEFORE the atomic block: both
            #   cards' network debits cannot be undone. One message covering each
            #   debited card (card, amount, transaction uuids), for a manual fix.
            uuids_des_transactions_legacy_c1 = []
            for transaction_legacy_c1 in transactions_legacy_c1:
                uuids_des_transactions_legacy_c1.append(str(transaction_legacy_c1[3]))
            uuids_des_transactions_legacy_c2 = []
            for transaction_legacy_c2 in transactions_legacy_c2:
                uuids_des_transactions_legacy_c2.append(str(transaction_legacy_c2[3]))

            debits_legacy_a_journaliser = []
            if transactions_legacy_c1:
                debits_legacy_a_journaliser.append(
                    f"carte1={carte1.tag_id} montant_legacy={montant_legacy_c1} "
                    f"transactions_legacy={', '.join(uuids_des_transactions_legacy_c1)}"
                )
            if transactions_legacy_c2:
                debits_legacy_a_journaliser.append(
                    f"carte2={carte2.tag_id} montant_legacy={montant_legacy_c2} "
                    f"transactions_legacy={', '.join(uuids_des_transactions_legacy_c2)}"
                )
            message_d_incident_legacy = ""
            if debits_legacy_a_journaliser:
                message_d_incident_legacy = (
                    f"INCIDENT legacy débité sans LigneArticle (2ème carte, atomic échoué) — "
                    f"uuid_transaction={uuid_transaction} "
                    f"{' ; '.join(debits_legacy_a_journaliser)} : "
                    f"régularisation manuelle requise."
                )

            # Carte2 couvre tout le reste (ou le reste est réglé en espèces / CB) →
            # bloc atomic
            # / Card2 covers all remainder (or the rest is paid in cash / CC) → atomic
            try:
                with db_transaction.atomic():
                    # Ouvrir la vente du paiement
                    # Une seule vente pour tout le paiement : ce que paient les deux
                    # cartes, ce que paie le réseau pour chacune, et le reste en
                    # espèces ou en CB. La clé d'idempotence est l'identifiant du
                    # paiement, le même que sur les lignes : un rejeu retrouve cette
                    # vente. Un panier en points n'arrive jamais ici (garde en tête de
                    # fonction) : la vente est en euros. Le client et la carte de la
                    # vente sont ceux de la carte 1.
                    # / Open the payment's sale: one sale for the whole payment. The
                    #   payment id is its idempotency key. Always in euros. Card 1 gives
                    #   the sale's customer and card.
                    vente = ouvrir_vente(
                        origine=SaleOrigin.LABOUTIK,
                        nature=Vente.Nature.VENTE,
                        point_de_vente=point_de_vente,
                        operateur=_operateur_de_la_caisse(
                            request, request.POST.get("tag_id_cm", "")
                        ),
                        client=carte1.user,
                        carte=carte1,
                        idempotency_key=str(uuid_transaction),
                    )

                    # Recharges gratuites
                    # Elles n'arrivent pas ici aujourd'hui : une recharge cadeau mêlée à
                    # d'autres articles est refusée en tête de fonction, et seule elle
                    # ne laisse rien à payer (sortie « le solde a changé »). Si une
                    # garde change, elles restent des articles de la MÊME vente, avec
                    # l'identifiant du paiement sur leurs lignes.
                    # / Free top-ups: unreachable today (guards above). If a guard
                    #   changes, they stay items of the SAME sale, with the payment id.
                    if articles_recharge_gratuite:
                        _executer_recharges(
                            articles_recharge_gratuite,
                            wallet_carte1,
                            carte1,
                            code_methode_paiement="gift",
                            ip_client=ip_client,
                            point_de_vente=point_de_vente,
                            vente=vente,
                            uuid_transaction=uuid_transaction,
                        )

                    # Débits non-fiduciaires carte1
                    # Ils n'arrivent pas ici aujourd'hui : un tarif non fiduciaire porte
                    # une monnaie de points ou de temps, et la garde en tête de fonction
                    # refuse un panier en points. Si elle change, chaque transaction
                    # reste un règlement de la vente, COPIÉ de la transaction renvoyée,
                    # avec la carte 1 et son portefeuille.
                    # / Card1 non-fiduciary debits: unreachable today (points guard). If
                    #   it changes, one payment per transaction, copied from it.
                    lignes_non_fidu = []
                    for article_nf in articles_non_fiduciaires:
                        asset_nf_cible = article_nf["price"].asset
                        montant_nf = (
                            article_nf["prix_centimes"] * article_nf["quantite"]
                        )
                        transaction_non_fiduciaire = TransactionService.creer_vente(
                            sender_wallet=wallet_carte1,
                            receiver_wallet=asset_nf_cible.wallet_origin,
                            asset=asset_nf_cible,
                            montant_en_centimes=montant_nf,
                            tenant=tenant_courant,
                            card=carte1,
                            ip=ip_client,
                        )
                        pm_nf = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[
                            asset_nf_cible.category
                        ]
                        ajouter_reglement(
                            vente,
                            moyen=pm_nf,
                            montant=transaction_non_fiduciaire.amount,
                            asset=asset_nf_cible.uuid,
                            carte=carte1,
                            wallet=wallet_carte1,
                            fedow_transaction_uuid=transaction_non_fiduciaire.uuid,
                        )
                        lignes_non_fidu.append(
                            (article_nf, asset_nf_cible, montant_nf, pm_nf)
                        )
                        assets_debites.add(asset_nf_cible)

                    # Débits cascade carte1 (lignes avec asset != None)
                    # / Card1 cascade debits (lines with asset != None)
                    debits_par_asset_c1 = OrderedDict()
                    for _art_c, asset_c, amount_c, _pm_c in lignes_nfc_carte1:
                        if asset_c is not None:
                            if asset_c not in debits_par_asset_c1:
                                debits_par_asset_c1[asset_c] = 0
                            debits_par_asset_c1[asset_c] += amount_c

                    # Un règlement par transaction : son montant et son uuid sont COPIÉS
                    # de la transaction renvoyée, jamais recalculés depuis les parts.
                    # Il porte la carte 1 et son portefeuille. Jetons cadeau : règlement
                    # « jetons » (LG), un vrai règlement (D8 bis).
                    # / One payment per transaction, copied from it, with card 1 and its
                    #   wallet. Gift tokens: LG.
                    for (
                        asset_a_debiter,
                        total_debit_asset,
                    ) in debits_par_asset_c1.items():
                        transaction_de_la_monnaie_c1 = TransactionService.creer_vente(
                            sender_wallet=wallet_carte1,
                            receiver_wallet=asset_a_debiter.wallet_origin,
                            asset=asset_a_debiter,
                            montant_en_centimes=total_debit_asset,
                            tenant=tenant_courant,
                            card=carte1,
                            ip=ip_client,
                        )
                        ajouter_reglement(
                            vente,
                            moyen=MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[
                                asset_a_debiter.category
                            ],
                            montant=transaction_de_la_monnaie_c1.amount,
                            asset=asset_a_debiter.uuid,
                            carte=carte1,
                            wallet=wallet_carte1,
                            fedow_transaction_uuid=transaction_de_la_monnaie_c1.uuid,
                        )

                    # Débits cascade carte2
                    # / Card2 cascade debits
                    debits_par_asset_c2 = OrderedDict()
                    for _art_c2, asset_c2, amount_c2, _pm_c2 in lignes_nfc_carte2:
                        if asset_c2 is not None:
                            if asset_c2 not in debits_par_asset_c2:
                                debits_par_asset_c2[asset_c2] = 0
                            debits_par_asset_c2[asset_c2] += amount_c2

                    # Même règle que pour la carte 1, mais chaque règlement porte la
                    # carte 2 et SON portefeuille : c'est elle qui a payé.
                    # / Same rule as card 1, but each payment carries card 2 and ITS
                    #   wallet: card 2 paid.
                    for (
                        asset_a_debiter_c2,
                        total_debit_c2,
                    ) in debits_par_asset_c2.items():
                        transaction_de_la_monnaie_c2 = TransactionService.creer_vente(
                            sender_wallet=wallet_carte2,
                            receiver_wallet=asset_a_debiter_c2.wallet_origin,
                            asset=asset_a_debiter_c2,
                            montant_en_centimes=total_debit_c2,
                            tenant=tenant_courant,
                            card=carte2,
                            ip=ip_client,
                        )
                        ajouter_reglement(
                            vente,
                            moyen=MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[
                                asset_a_debiter_c2.category
                            ],
                            montant=transaction_de_la_monnaie_c2.amount,
                            asset=asset_a_debiter_c2.uuid,
                            carte=carte2,
                            wallet=wallet_carte2,
                            fedow_transaction_uuid=transaction_de_la_monnaie_c2.uuid,
                        )

                    # Règlements des débits legacy (faits plus haut, hors atomic)
                    # Un règlement par transaction du réseau, lu dans les transactions
                    # renvoyées et non dans les parts (une part a perdu le lien avec sa
                    # transaction). Chaque règlement porte la carte débitée : la carte 1
                    # pour ses transactions, la carte 2 pour les siennes. La transaction
                    # vit sur le serveur Fedow distant : son uuid va dans
                    # `reference_externe` (`fedow_transaction_uuid` est réservé aux
                    # transactions `fedow_core` locales).
                    # / One payment per network transaction, with the debited card.
                    #   Remote transaction: its uuid goes to reference_externe.
                    for transaction_legacy_c1 in transactions_legacy_c1:
                        ajouter_reglement(
                            vente,
                            moyen=transaction_legacy_c1[2],
                            montant=transaction_legacy_c1[1],
                            asset=transaction_legacy_c1[0],
                            carte=carte1,
                            reference_externe=str(transaction_legacy_c1[3]),
                        )
                    for transaction_legacy_c2 in transactions_legacy_c2:
                        ajouter_reglement(
                            vente,
                            moyen=transaction_legacy_c2[2],
                            montant=transaction_legacy_c2[1],
                            asset=transaction_legacy_c2[0],
                            carte=carte2,
                            reference_externe=str(transaction_legacy_c2[3]),
                        )

                    # Règlement du reste après les deux cartes, en espèces ou en CB
                    # UN règlement du reste dû, jamais la somme donnée par le client :
                    # la monnaie rendue n'est pas un règlement. Pas de règlement de 0 :
                    # quand les cartes couvrent tout, il n'y a pas de reste.
                    # / ONE payment of the amount due, never the amount handed over.
                    #   No 0 payment: when the cards cover everything, there is no rest.
                    if lignes_reste_apres_carte2:
                        ajouter_reglement(
                            vente,
                            moyen=pm_reste,
                            montant=total_reste_apres_carte2,
                        )

                    # Créer les LigneArticle pour carte1 (lignes NFC couvertes)
                    # / Create LigneArticle for card1 (covered NFC lines)
                    lignes_couvertes_c1 = [
                        (art, asset, amount, pm)
                        for art, asset, amount, pm in lignes_nfc_carte1
                        if asset is not None
                    ]
                    lignes_couvertes_c2 = [
                        (art, asset, amount, pm)
                        for art, asset, amount, pm in lignes_nfc_carte2
                        if asset is not None
                    ]

                    # + lignes_legacy_c2 : parts couvertes par le FED de la carte2 (débit déjà fait
                    # hors atomic), avec leur moyen résolu (STRIPE_FED / LOCAL_EURO) et l'uuid distant.
                    # / + lignes_legacy_c2: card2 FED-covered parts (already debited outside atomic).
                    # + lignes_reste_apres_carte2 : le reste regle en especes / CB.
                    # / + remainder paid in cash / CC.
                    toutes_les_lignes = (
                        lignes_non_fidu
                        + lignes_couvertes_c1
                        + lignes_couvertes_c2
                        + lignes_legacy_c1
                        + lignes_legacy_c2
                        + lignes_reste_apres_carte2
                    )
                    # Chaque part est un article de la vente. Les lignes gardent la
                    # carte 1, même pour les parts payées par la carte 2 : seuls les
                    # règlements disent quelle carte a payé.
                    # / Each part is an item of the sale. The lines keep card 1; only
                    #   the payments say which card paid.
                    lignes_creees, produits_stock_negatif = (
                        _creer_lignes_articles_cascade(
                            lignes_pre_calculees=toutes_les_lignes,
                            carte=carte1,
                            carte_complement=carte2,
                            wallet=wallet_carte1,
                            uuid_transaction=uuid_transaction,
                            point_de_vente=point_de_vente,
                            vente=vente,
                        )
                    )

                    # Adhésions
                    # / Memberships
                    if articles_adhesion:
                        lignes_par_product = {}
                        for ligne_creee in lignes_creees:
                            product_uuid_str = str(
                                ligne_creee.pricesold.productsold.product.uuid
                            )
                            if product_uuid_str not in lignes_par_product:
                                lignes_par_product[product_uuid_str] = ligne_creee

                        for article_ad in articles_adhesion:
                            membership = _creer_ou_renouveler_adhesion(
                                carte1.user,
                                article_ad["product"],
                                article_ad["price"],
                            )
                            if membership:
                                product_uuid_ad = str(article_ad["product"].uuid)
                                ligne_ad = lignes_par_product.get(product_uuid_ad)
                                if ligne_ad:
                                    ligne_ad.membership = membership
                                    ligne_ad.save(update_fields=["membership"])
                                _appliquer_les_effets_d_une_adhesion_vendue_en_caisse(
                                    membership, ligne_ad
                                )

                    # Encaisser la vente, EN DERNIER
                    # `encaisser_vente` vérifie les deux égalités et pose le numéro. Si
                    # elles ne tiennent pas, il lève `EgaliteDeVenteRompue` : tout le bloc
                    # est annulé (lignes, débits locaux des deux cartes, adhésions).
                    # / Settle the sale, LAST: a broken equality rolls back the block.
                    encaisser_vente(vente)

            except SoldeInsuffisant:
                # INCIDENT rarissime : le legacy d'une carte (ou des deux) a été débité
                # hors atomic, puis l'atomic local a échoué : l'argent du réseau est
                # prélevé SANS vente ni ligne. On JOURNALISE pour une régularisation à la
                # main (le legacy ne s'annule pas automatiquement).
                # / Rare INCIDENT: legacy debited, local atomic failed → log for manual fix.
                if message_d_incident_legacy:
                    logger.error(message_d_incident_legacy)
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _(
                        "Solde insuffisant. Le solde a changé depuis la lecture."
                    ),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request, "laboutik/partial/hx_messages.html", context_erreur
                )

            # Cet `except` vient AVANT `except Exception` : sinon l'égalité rompue
            # partirait en erreur 500.
            # / This `except` comes BEFORE `except Exception`: otherwise a 500.
            except EgaliteDeVenteRompue as erreur_d_egalite:
                # Les règlements ne couvrent pas exactement les articles : le bloc atomic
                # a tout annulé (lignes, débits locaux, adhésions). Les débits legacy,
                # faits avant, restent : même journal d'incident que pour un solde
                # insuffisant. La caisse montre son écran d'erreur, jamais une erreur 500.
                # / Broken equality: the atomic block rolled everything back. The legacy
                #   debits stay: same incident log. The register shows its error screen.
                if message_d_incident_legacy:
                    logger.error(message_d_incident_legacy)
                logger.error(
                    f"Vente 2ème carte refusée (égalité rompue) — "
                    f"uuid_transaction={uuid_transaction} carte1={carte1.tag_id} "
                    f"carte2={carte2.tag_id} : {erreur_d_egalite}"
                )
                context_erreur = {
                    "action": "initUrlAddition();",
                    "msg_type": "warning",
                    "msg_content": _(
                        "Le paiement n'a pas été enregistré : la vente est incohérente. "
                        "Prévenez un responsable du lieu."
                    ),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request,
                    "laboutik/partial/hx_messages.html",
                    context_erreur,
                    status=409,
                )

            except Exception as e:
                # Toute AUTRE exception dans l'atomic : le local est annulé, mais les
                # débits du réseau (d'une carte ou des deux), faits avant, restent
                # prélevés SANS vente ni ligne. On JOURNALISE l'incident avec le message
                # préparé avant l'atomic (pour chaque carte débitée : la carte, le
                # montant, les uuid), plus l'exception, puis on relaie l'exception
                # (500 volontaire). Pas de journalisation en base.
                # / Any OTHER exception in the atomic: the network debits of one or both
                #   cards stay taken without a sale. Log the prepared incident message
                #   plus the exception, then re-raise (500).
                if message_d_incident_legacy:
                    logger.error(
                        f"{message_d_incident_legacy} Exception imprévue dans l'atomic : {e}"
                    )
                raise

            # Succès 2ème carte → avant / apres, un cadre par carte a l'ecran.
            # Les non-fiduciaires sont débités sur la carte 1.
            # / 2nd card success → before / after, one frame per card on screen.
            soldes_carte1 = _calculer_soldes_apres_paiement(
                wallet=wallet_carte1,
                lignes_debitees=lignes_non_fidu + lignes_couvertes_c1,
            )
            soldes_carte2 = _calculer_soldes_apres_paiement(
                wallet=wallet_carte2,
                lignes_debitees=lignes_couvertes_c2,
            )

            # Une entree par carte qui a vraiment paye en local
            # / One entry per card that actually paid locally
            cartes_apres_paiement = []
            if soldes_carte1:
                cartes_apres_paiement.append(
                    {"tag_id": tag_id_carte1, "soldes": soldes_carte1}
                )
            if soldes_carte2:
                cartes_apres_paiement.append(
                    {"tag_id": tag_id_carte2, "soldes": soldes_carte2}
                )

            # Liste a plat, gardee pour nouveau_solde / monnaie_name
            # / Flat list, kept for nouveau_solde / monnaie_name
            soldes_apres_paiement = soldes_carte1 + soldes_carte2

            nouveau_solde_euros = None
            nom_monnaie_principal = ""
            if soldes_apres_paiement:
                nouveau_solde_euros = soldes_apres_paiement[0]["solde_euros"]
                nom_monnaie_principal = soldes_apres_paiement[0]["name"]

            # Moyen affiche : « NFC » si les cartes ont tout paye, sinon
            # « NFC / especes » ou « NFC / CB » comme la branche especes/CB.
            # / Shown method: "NFC", or "NFC / cash|CC" when the rest was paid otherwise.
            if lignes_reste_apres_carte2:
                moyen_paiement_affiche = moyen_reste_apres_carte2
                original_payment_affiche = True
            else:
                moyen_paiement_affiche = _("NFC")
                original_payment_affiche = None

            context_succes = {
                "currency_data": CURRENCY_DATA,
                "payment": donnees_paiement,
                "monnaie_name": nom_monnaie_principal,
                "moyen_paiement": moyen_paiement_affiche,
                "original_payment": original_payment_affiche,
                "original_moyen_paiement": _("NFC"),
                "deposit_is_present": False,
                "total": total_centimes / 100,
                "state": state,
                "nouveau_solde": nouveau_solde_euros,
                "card_name": carte1.tag_id,
                "uuid_transaction": str(uuid_transaction),
                "uuid_vente": _uuid_de_la_vente_du_paiement(uuid_transaction),
                "uuid_pv": str(point_de_vente.uuid),
                "soldes_apres_paiement": soldes_apres_paiement,
                "cartes_apres_paiement": cartes_apres_paiement,
                "produits_stock_negatif": produits_stock_negatif,
            }
            return render(
                request,
                "laboutik/partial/hx_return_payment_success.html",
                context_succes,
            )

        # Moyen de complément non reconnu
        # / Unrecognized complement method
        context_erreur = {
            "action": "initUrlAddition();",
            "msg_type": "warning",
            "msg_content": _("Moyen de complément non reconnu"),
            "selector_bt_retour": "#messages",
        }
        return render(
            request, "laboutik/partial/hx_messages.html", context_erreur, status=400
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="verifier_carte",
        url_name="verifier_carte",
    )
    def verifier_carte(self, request):
        """
        GET /laboutik/paiement/verifier_carte/
        Affiche le partial d'attente de lecture NFC (pour vérification de solde).
        Displays the NFC read waiting partial (for balance check).
        """
        return render(request, "laboutik/partial/hx_check_card.html", {})

    @action(
        detail=False, methods=["post"], url_path="retour_carte", url_name="retour_carte"
    )
    def retour_carte(self, request):
        """
        POST /laboutik/paiement/retour_carte/
        Reçoit le tag NFC scanné et retourne le feedback de la carte :
        solde réel (fedow_core), type (fédérée/anonyme), adhésions actives.
        Receives the scanned NFC tag and returns card feedback:
        real balance (fedow_core), type (federated/anonymous), active memberships.
        """
        state = _construire_state(user=request.user)
        tag_id_scanne = request.POST.get("tag_id", "").strip().upper()

        # 1. Chercher la carte par tag_id
        # 1. Find the card by tag_id
        try:
            carte = CarteCashless.objects.get(tag_id=tag_id_scanne)
        except CarteCashless.DoesNotExist:
            context = {
                "card": {"email": None},
                "total_monnaie": 0,
                "tokens": [],
                "adhesions": [],
                "tag_id": tag_id_scanne,
                "background": "--error",
                "state": state,
                "erreur": _("Carte inconnue"),
            }
            return render(request, "laboutik/partial/hx_card_feedback.html", context)

        # 2. + 3. Solde complet de la carte : monnaies locales (fedow_core) + FED réseau (Fedow).
        #    Le helper lit les locaux en base et le FED frais sur le Fedow distant (si carte liée).
        # 2. + 3. Card full balance: local currencies (fedow_core) + FED network (Fedow).
        solde = obtenir_solde_complet_carte(carte)
        tokens = solde["tokens_locaux"]

        # 4. Adhésions actives (si user connu)
        # 4. Active memberships (if user known)
        adhesions = []
        if carte.user:
            # CANCELED n'est PAS exclu ici : une adhesion resiliee court
            # jusqu'a sa deadline (l'adherent a paye sa periode), et c'est
            # is_valid() qui tranche. L'exclure au niveau SQL priverait
            # l'adherent de son adhesion des la resiliation.
            # ADMIN_CANCELED reste exclu : annulation administrative, effet
            # immediat, avoir possible.
            # / CANCELED is NOT excluded here: a cancelled membership runs
            # until its deadline and is_valid() decides. ADMIN_CANCELED stays
            # excluded: admin cancellation is immediate.
            toutes_adhesions = list(
                Membership.objects.filter(
                    user=carte.user,
                )
                .exclude(
                    status=Membership.ADMIN_CANCELED,
                )
                .select_related("price__product")
            )
            adhesions = [m for m in toutes_adhesions if m.is_valid()]

        # 5. Couleur de fond selon le type de carte
        # 5. Background color based on card type
        email_carte = carte.user.email if carte.user else None
        prenom_carte = carte.user.first_name if carte.user else None
        couleur_fond = "--success" if email_carte else "--warning"

        # 6. Zone « Recharger » : les produits de recharge du point de vente courant.
        #    uuid_pv et tag_id_cm viennent de #addition-form (hx-include sur
        #    #form-check-nfc, voir hx_check_card.html).
        #    La zone ne s'affiche que si la carte primaire a un PV cashless,
        #    et seulement avec un PV valide.
        # 6. "Top up" zone: the current POS top-up products. uuid_pv and tag_id_cm
        #    come from #addition-form. Shown only if the primary card has a
        #    cashless POS, and only with a valid POS.
        tag_id_carte_primaire = request.POST.get("tag_id_cm", "").strip().upper()
        la_recharge_est_permise = _carte_primaire_a_un_point_de_vente_cashless(
            tag_id_carte_primaire
        )

        point_de_vente_courant = None
        uuid_pv_recu = request.POST.get("uuid_pv", "").strip()
        if uuid_pv_recu and la_recharge_est_permise:
            try:
                point_de_vente_courant = PointDeVente.objects.get(uuid=uuid_pv_recu)
            except (PointDeVente.DoesNotExist, ValueError, DjangoValidationError):
                point_de_vente_courant = None
        contexte_recharge = _construire_contexte_recharge(carte, point_de_vente_courant)

        context = {
            "card": {"email": email_carte, "first_name": prenom_carte},
            "total_monnaie": solde["total_centimes"] / 100,
            "tokens": tokens,
            "fed_euros": solde["fed_centimes"] / 100,
            "fed_disponible": solde["fed_disponible"],
            "adhesions": adhesions,
            "tag_id": tag_id_scanne,
            "background": couleur_fond,
            "state": state,
            "recharge": contexte_recharge,
            "currency_data": CURRENCY_DATA,
        }
        return render(request, "laboutik/partial/hx_card_feedback.html", context)

    @action(
        detail=False,
        methods=["get"],
        url_path="recharge_carte",
        url_name="recharge_carte",
    )
    def recharge_carte(self, request):
        """
        GET /laboutik/paiement/recharge_carte/
        Renvoie la zone « Recharger » de la popup check carte, a l'etape demandee.
        / Returns the "Top up" zone of the card check popup, at the requested step.

        LOCALISATION : laboutik/views.py

        FLUX :
        1. hx_card_feedback.html inclut hx_card_recharge.html (etape 1 : quoi)
        2. Chaque tuile / bouton de la zone fait un hx-get ici avec :
           tag_id, uuid_pv, produit, prix, montant (montant libre en euros)
        3. On recalcule la zone avec _construire_contexte_recharge()
        4. Le partial remplace #card-recharge-zone (outerHTML)
        La recharge elle-meme part ensuite vers payer() (RE) ou
        identifier_client() (RC / TM) : rien n'est ecrit en base ici.
        / Each tap re-renders the zone. Nothing is written to the DB here.
        """
        tag_id_de_la_carte = request.GET.get("tag_id", "").strip().upper()
        uuid_pv_recu = request.GET.get("uuid_pv", "").strip()
        uuid_produit_choisi = request.GET.get("produit", "").strip()
        uuid_prix_choisi = request.GET.get("prix", "").strip()

        carte = get_object_or_404(CarteCashless, tag_id=tag_id_de_la_carte)

        point_de_vente_courant = None
        if uuid_pv_recu:
            try:
                point_de_vente_courant = PointDeVente.objects.get(uuid=uuid_pv_recu)
            except (PointDeVente.DoesNotExist, ValueError, DjangoValidationError):
                point_de_vente_courant = None

        # Premier passage : on construit sans montant libre pour connaitre le tarif choisi
        # / First pass without free amount, to know the chosen price
        contexte_recharge = _construire_contexte_recharge(
            carte,
            point_de_vente_courant,
            uuid_produit_choisi=uuid_produit_choisi,
            uuid_prix_choisi=uuid_prix_choisi,
        )

        # Montant libre envoye : on le valide (serializer), minimum = prix de base du tarif
        # / Free amount sent: validate it (serializer), minimum = base price
        montant_libre_envoye = "montant" in request.GET
        tarif_choisi = contexte_recharge["tarif_choisi"]
        if montant_libre_envoye and tarif_choisi and tarif_choisi["est_libre"]:
            minimum_centimes = int(round(tarif_choisi["minimum_euros"] * 100))
            serializer_montant = RechargeMontantLibreSerializer(
                data={"montant": request.GET.get("montant", "")},
                context={"minimum_centimes": minimum_centimes},
            )
            if serializer_montant.is_valid():
                contexte_recharge = _construire_contexte_recharge(
                    carte,
                    point_de_vente_courant,
                    uuid_produit_choisi=uuid_produit_choisi,
                    uuid_prix_choisi=uuid_prix_choisi,
                    montant_libre_saisi=serializer_montant.validated_data["montant"],
                )
            else:
                contexte_recharge["erreur_montant"] = serializer_montant.errors["montant"][0]
                contexte_recharge["montant_saisi"] = request.GET.get("montant", "")

        return render(
            request,
            "laboutik/partial/hx_card_recharge.html",
            {"recharge": contexte_recharge, "currency_data": CURRENCY_DATA},
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="vider_carte/overlay",
        url_name="vider_carte_overlay",
    )
    def vider_carte_overlay(self, request):
        """
        GET /laboutik/paiement/vider_carte/overlay/
        Rend l'overlay de scan NFC pour vider carte.
        / Renders the NFC scan overlay for card refund.
        """
        uuid_pv = request.GET.get("uuid_pv", "")
        tag_id_cm = request.GET.get("tag_id_cm", "")

        pv = None
        if uuid_pv:
            pv = PointDeVente.objects.filter(uuid=uuid_pv).first()

        # Contexte minimal : pv + card.tag_id via tag_id_cm query param.
        # / Minimal context: pv + card.tag_id via tag_id_cm query param.
        contexte = {
            "pv": pv,
            "card": {"tag_id": tag_id_cm},
        }
        return render(
            request,
            "laboutik/partial/hx_vider_carte_overlay.html",
            contexte,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="vider_carte/preview",
        url_name="vider_carte_preview",
    )
    def vider_carte_preview(self, request):
        """
        POST /laboutik/paiement/vider_carte/preview/
        Montre ce que le vidage reprendra, séparé par Fedow, et l'argent à rendre.
        Rien n'est débité, ni en local ni sur l'ancien Fedow.
        / Shows what the emptying will take back, split by Fedow, and the cash to give
        back. Nothing is debited.

        FLUX :
        1. Gardes (carte primaire scannée, carte inconnue).
        2. Fedow local : les jetons que `WalletService.rembourser_en_especes` reprendra
           (monnaie locale et jetons cadeau du lieu, monnaie fédérée), lus en base.
        3. Ancien Fedow : `_lire_la_carte_sur_l_ancien_fedow` (lecture seule).
        4. Refus seulement si la vidange refuserait aussi : rien à reprendre nulle part,
           carte inconnue de l'ancien Fedow (ou lieu non relié), ancien Fedow joignable.
           Une carte vide partout mais connue de l'ancien Fedow s'accepte : « vider et
           délier » la délie des deux côtés.
        / Refused only when the emptying would refuse too.
        """
        from django.db.models import Q
        from fedow_core.models import Token

        tag_id = request.POST.get("tag_id", "").strip().upper()
        tag_id_cm = request.POST.get("tag_id_cm", "").strip().upper()
        uuid_pv = request.POST.get("uuid_pv", "")

        # Protection self-refund.
        if tag_id and tag_id == tag_id_cm:
            return _render_erreur_toast(
                request,
                _("Ne peut pas vider une carte primaire."),
            )

        try:
            carte = CarteCashless.objects.get(tag_id=tag_id)
        except CarteCashless.DoesNotExist:
            return _render_erreur_toast(request, _("Carte client inconnue."))

        # 2. Fedow local : même portefeuille et même filtre que le vidage
        # (fedow_core/services.py, `rembourser_en_especes`). On ne crée pas de
        # portefeuille : une carte sans portefeuille n'a aucun jeton local.
        # / Local Fedow: same wallet and filter as the emptying. No wallet is created.
        portefeuille_de_la_carte = None
        if carte.user is not None and carte.user.wallet is not None:
            portefeuille_de_la_carte = carte.user.wallet
        elif carte.wallet_ephemere is not None:
            portefeuille_de_la_carte = carte.wallet_ephemere

        jetons_locaux = []
        if portefeuille_de_la_carte is not None:
            jetons_locaux = list(
                Token.objects.filter(
                    wallet=portefeuille_de_la_carte,
                    value__gt=0,
                )
                .filter(
                    Q(asset__category=Asset.TLF, asset__tenant_origin=connection.tenant)
                    | Q(asset__category=Asset.TNF, asset__tenant_origin=connection.tenant)
                    | Q(asset__category=Asset.FED)
                )
                .select_related("asset")
                .order_by("asset__category", "asset__name")
            )

        lignes_fedow_local = []
        for jeton_local in jetons_locaux:
            lignes_fedow_local.append(
                _ligne_de_vidage(
                    jeton_local.asset.name,
                    jeton_local.value,
                    jeton_local.asset.category,
                    jeton_local.asset.currency_code,
                )
            )

        # 3. Ancien Fedow, en lecture seule.
        # / Old Fedow, read only.
        carte_sur_l_ancien_fedow = _lire_la_carte_sur_l_ancien_fedow(carte)
        lignes_ancien_fedow = []
        for jeton_distant in carte_sur_l_ancien_fedow.jetons:
            lignes_ancien_fedow.append(
                _ligne_de_vidage(
                    jeton_distant["asset_name"],
                    jeton_distant["value"],
                    jeton_distant["asset_category"],
                    jeton_distant["asset"].get("currency_code") or "",
                )
            )

        # 4. Refus seulement si la vidange refuserait aussi.
        # / Refused only when the emptying would refuse too.
        il_y_a_quelque_chose_a_reprendre = bool(lignes_fedow_local or lignes_ancien_fedow)
        carte_connue_de_l_ancien_fedow = carte_sur_l_ancien_fedow.statut == "connue"
        ancien_fedow_injoignable = carte_sur_l_ancien_fedow.statut == "injoignable"
        if (
            not il_y_a_quelque_chose_a_reprendre
            and not carte_connue_de_l_ancien_fedow
            and not ancien_fedow_injoignable
        ):
            return _render_erreur_toast(
                request,
                _("Aucun solde remboursable sur cette carte."),
            )

        argent_a_rendre_en_centimes = 0
        for ligne in lignes_fedow_local + lignes_ancien_fedow:
            if ligne.est_de_l_argent_rendu:
                argent_a_rendre_en_centimes += ligne.montant_centimes

        contexte = {
            "carte": carte,
            "lignes_fedow_local": lignes_fedow_local,
            "lignes_ancien_fedow": lignes_ancien_fedow,
            "ancien_fedow_injoignable": ancien_fedow_injoignable,
            "il_y_a_quelque_chose_a_reprendre": il_y_a_quelque_chose_a_reprendre,
            "total_centimes": argent_a_rendre_en_centimes,
            "tag_id": tag_id,
            "tag_id_cm": tag_id_cm,
            "uuid_pv": uuid_pv,
        }
        return render(
            request,
            "laboutik/partial/hx_vider_carte_confirm.html",
            contexte,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="vider_carte",
        url_name="vider_carte",
    )
    def vider_carte(self, request):
        """
        POST /laboutik/paiement/vider_carte/
        Vide la carte du client sur les DEUX Fedow, et écrit la vente du vidage.
        Renvoie l'ecran de succes ou un toast d'erreur.
        / Empties the customer card on BOTH Fedow servers and writes the sale.
        Returns the success screen or an error toast.

        FLUX :
        1. Gardes (carte client, carte primaire, point de vente).
        2. Ancien Fedow, hors transaction : `_vider_la_carte_sur_l_ancien_fedow`.
           Échec → rien n'est fait, toast d'erreur. Vidé là-bas mais réponse
           illisible → rien n'est écrit en local, toast qui dit la vérité (vidée sur
           l'ancien Fedow, pas en local, incident enregistré).
        3. Un seul `atomic` : `WalletService.rembourser_en_especes` (Fedow local et
           lignes « Refund » des deux Fedow), `_ecrire_la_vente_du_vidage`, puis
           `encaisser_vente` EN DERNIER. Échec après un vidage distant → journal
           INCIDENT, toast d'erreur.
        La vidange se fait dès qu'un des deux Fedow a quelque chose à reprendre.
        / Old Fedow first (failure: nothing done), then one atomic block for the local
        emptying, the sale and its settlement (failure after a remote emptying: INCIDENT).
        """
        from fedow_core.exceptions import NoEligibleTokens

        serializer = ViderCarteSerializer(data=request.POST)
        serializer.is_valid(raise_exception=True)

        tag_id_client = serializer.validated_data["tag_id"]
        tag_id_cm = serializer.validated_data["tag_id_cm"]
        uuid_pv = serializer.validated_data["uuid_pv"]
        vider_carte_flag = serializer.validated_data["vider_carte"]

        # Protection self-refund (meme check qu'en preview).
        # / Self-refund protection (same check as preview).
        if tag_id_client == tag_id_cm:
            return _render_erreur_toast(
                request,
                _("Ne peut pas vider une carte primaire."),
            )

        try:
            carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
        except CarteCashless.DoesNotExist:
            return _render_erreur_toast(request, _("Carte client inconnue."))

        carte_primaire_obj, erreur_cp = _charger_carte_primaire(tag_id_cm)
        if erreur_cp:
            return _render_erreur_toast(request, erreur_cp)

        pv = PointDeVente.objects.filter(uuid=uuid_pv).first()
        if pv is None:
            return _render_erreur_toast(request, _("PV introuvable."))

        # Controle d'acces : la carte primaire doit pouvoir operer sur ce PV.
        # / Access control: primary card must have access to this POS.
        if not pv.cartes_primaires.filter(pk=carte_primaire_obj.pk).exists():
            return _render_erreur_toast(
                request,
                _("Cette carte caissier n'a pas acces a ce PV."),
            )

        receiver_wallet = WalletService.get_or_create_wallet_tenant(connection.tenant)

        # 1. L'ancien Fedow d'abord, HORS de la transaction de base (appel réseau,
        # il ne s'annule pas). S'il échoue, rien n'est fait.
        # / 1. The old Fedow first, OUTSIDE the database transaction. If it fails,
        # nothing is done.
        try:
            reponse_de_l_ancien_fedow = _vider_la_carte_sur_l_ancien_fedow(
                carte_client,
                carte_primaire_obj.carte.tag_id,
                vider_carte_flag,
            )
        except CarteVideeSurLAncienFedowReponseIllisible:
            # La carte EST vidée sur l'ancien Fedow : « réessayez » serait faux. Le
            # helper a déjà journalisé l'INCIDENT. Rien n'est écrit en local.
            # / The card IS emptied on the old Fedow: "retry" would be false. The
            # helper already logged the INCIDENT. Nothing is written locally.
            return _render_erreur_toast(
                request,
                _(
                    "La carte est vidée sur l'ancien Fedow, mais pas en local. "
                    "Incident enregistré : prévenez un responsable."
                ),
            )
        except Exception as erreur_ancien_fedow:
            logger.warning(
                f"Vidage de la carte {carte_client.tag_id} sur l'ancien Fedow échoué, "
                f"rien n'est fait : {erreur_ancien_fedow}"
            )
            return _render_erreur_toast(
                request,
                _("L'ancien Fedow n'a pas pu vider la carte. Rien n'a été fait : réessayez."),
            )

        # None : la carte n'a pas été envoyée à l'ancien Fedow (lieu non relié, carte
        # inconnue là-bas). Sinon, `card/refund` a réussi (REFUND ou VOID).
        # / None: the card was not sent to the old Fedow. Otherwise card/refund succeeded.
        carte_videe_sur_l_ancien_fedow = reponse_de_l_ancien_fedow is not None
        transactions_de_l_ancien_fedow = []
        if carte_videe_sur_l_ancien_fedow:
            transactions_de_l_ancien_fedow = reponse_de_l_ancien_fedow

        # Argent repris sur l'ancien Fedow (monnaie locale du lieu, monnaie fédérée).
        # Les jetons cadeau sont repris sans argent.
        # / Money taken back on the old Fedow. Gift tokens carry no money.
        total_tlf_ancien_fedow = 0
        total_fed_ancien_fedow = 0
        uuid_fed_ancien_fedow = None
        uuids_des_transactions_de_l_ancien_fedow = []
        for transaction_distante in transactions_de_l_ancien_fedow:
            uuids_des_transactions_de_l_ancien_fedow.append(str(transaction_distante["uuid"]))
            if transaction_distante["categorie"] == "TLF":
                total_tlf_ancien_fedow += transaction_distante["montant"]
            elif transaction_distante["categorie"] == "FED":
                total_fed_ancien_fedow += transaction_distante["montant"]
                uuid_fed_ancien_fedow = transaction_distante["asset"]
        ancien_fedow_a_repris_des_jetons = len(transactions_de_l_ancien_fedow) > 0

        # Le journal d'incident, préparé AVANT le bloc atomic : l'ancien Fedow est déjà
        # vidé (ou la carte déliée). Si le vidage local échoue, ce message permet de
        # régulariser à la main (montant, carte, uuid de chaque transaction distante).
        # / The incident log, prepared BEFORE the atomic block: the old Fedow is already
        # emptied (or the card unlinked). If the local emptying fails: manual fix.
        message_d_incident_ancien_fedow = ""
        if carte_videe_sur_l_ancien_fedow:
            message_d_incident_ancien_fedow = (
                f"INCIDENT ancien Fedow vidé sans vidage local (atomic local échoué) — "
                f"carte={carte_client.tag_id} "
                f"montant_argent={total_tlf_ancien_fedow + total_fed_ancien_fedow} "
                f"transactions_ancien_fedow="
                f"{', '.join(uuids_des_transactions_de_l_ancien_fedow)} : "
                f"régularisation manuelle requise."
            )

        # Le titulaire de la carte, lu AVANT le vidage : « vider et délier » le retire.
        # / The card holder, read BEFORE the emptying: "empty and unlink" removes it.
        client_de_la_vente = carte_client.user

        # 2. Un seul bloc atomic : vidage local, vente du vidage, encaissement EN DERNIER.
        # / 2. One atomic block: local emptying, sale, settlement LAST.
        try:
            with db_transaction.atomic():
                resultat = WalletService.rembourser_en_especes(
                    carte=carte_client,
                    tenant=connection.tenant,
                    receiver_wallet=receiver_wallet,
                    ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                    vider_carte=vider_carte_flag,
                    primary_card=carte_primaire_obj.carte,
                    total_tlf_ancien_fedow_centimes=total_tlf_ancien_fedow,
                    total_fed_ancien_fedow_centimes=total_fed_ancien_fedow,
                    uuid_fed_ancien_fedow=uuid_fed_ancien_fedow,
                    ancien_fedow_a_repris_des_jetons=ancien_fedow_a_repris_des_jetons,
                    carte_videe_sur_l_ancien_fedow=carte_videe_sur_l_ancien_fedow,
                )
                vente_du_vidage = _ecrire_la_vente_du_vidage(
                    request,
                    pv,
                    carte_client,
                    client_de_la_vente,
                    resultat["transactions"],
                    transactions_de_l_ancien_fedow,
                )
                if vente_du_vidage is not None:
                    encaisser_vente(vente_du_vidage)
        except NoEligibleTokens:
            # Rien à reprendre, ni en local ni sur l'ancien Fedow.
            # / Nothing to take back, locally or on the old Fedow.
            return _render_erreur_toast(
                request,
                _("Aucun solde remboursable (solde a pu changer)."),
            )
        except Exception:
            # Sans vidage distant, l'erreur remonte comme avant. Après un vidage
            # distant, la carte est vidée là-bas sans trace locale : INCIDENT
            # journalisé, écran d'erreur.
            # / Without a remote emptying, the error is raised as before. After one:
            # INCIDENT logged, error screen.
            if not carte_videe_sur_l_ancien_fedow:
                raise
            logger.exception(message_d_incident_ancien_fedow)
            return _render_erreur_toast(
                request,
                _(
                    "La carte est vidée sur l'ancien Fedow, mais pas en local. "
                    "Incident enregistré : prévenez un responsable."
                ),
            )

        argent_rendu_ancien_fedow = total_tlf_ancien_fedow + total_fed_ancien_fedow

        # Le détail séparé par Fedow, une ligne par monnaie reprise, pour l'écran.
        # / The detail split by Fedow, one line per currency, for the screen.
        lignes_fedow_local = []
        for transaction_locale in resultat["transactions"]:
            lignes_fedow_local.append(
                _ligne_de_vidage(
                    transaction_locale.asset.name,
                    transaction_locale.amount,
                    transaction_locale.asset.category,
                    transaction_locale.asset.currency_code,
                )
            )
        lignes_ancien_fedow = []
        for transaction_distante in transactions_de_l_ancien_fedow:
            lignes_ancien_fedow.append(
                _ligne_de_vidage(
                    transaction_distante["nom"],
                    transaction_distante["montant"],
                    transaction_distante["categorie"],
                    transaction_distante["code_monnaie"],
                )
            )

        contexte = {
            # Argent à rendre au client : les deux Fedow.
            # / Money to hand back: both Fedow servers.
            "total_centimes": resultat["total_centimes"] + argent_rendu_ancien_fedow,
            "total_tlf_centimes": resultat["total_tlf_centimes"] + total_tlf_ancien_fedow,
            "total_fed_centimes": resultat["total_fed_centimes"] + total_fed_ancien_fedow,
            "lignes_articles": resultat["lignes_articles"],
            "transaction_uuids": [str(tx.uuid) for tx in resultat["transactions"]],
            "uuid_pv": uuid_pv,
            "vider_carte": vider_carte_flag,
            # Le détail séparé par Fedow, pour l'écran et le reçu détaillés. Le reçu
            # ne reçoit que des uuid : il relit chaque transaction.
            # / The detail split by Fedow. The receipt only gets uuids: it re-reads.
            "transactions_fedow_local": resultat["transactions"],
            "transactions_ancien_fedow": transactions_de_l_ancien_fedow,
            "lignes_fedow_local": lignes_fedow_local,
            "lignes_ancien_fedow": lignes_ancien_fedow,
            "transaction_uuids_ancien_fedow": uuids_des_transactions_de_l_ancien_fedow,
        }
        return render(
            request,
            "laboutik/partial/hx_vider_carte_success.html",
            contexte,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="vider_carte/imprimer_recu",
        url_name="vider_carte_imprimer_recu",
    )
    def vider_carte_imprimer_recu(self, request):
        """
        POST /laboutik/paiement/vider_carte/imprimer_recu/
        Imprime le reçu d'un vidage de carte, séparé par Fedow et détaillé.
        / Prints a card-emptying receipt, split by Fedow and detailed.

        FLUX :
        1. Reçoit des uuid seulement : `transaction_uuids` (Fedow local) et
           `transaction_uuids_ancien_fedow` (ancien Fedow). Jamais de montant.
        2. Fedow local : les transactions de remboursement relues en base.
        3. Ancien Fedow : `_relire_les_transactions_de_l_ancien_fedow`. S'il ne répond
           pas, l'impression est refusée : jamais de reçu partiel.
        4. `formatter_recu_vider_carte`, puis l'impression Celery.
        / Only uuids are posted; every transaction is re-read. Old Fedow unreachable:
        printing refused, never a partial receipt.
        """
        transaction_uuids = request.POST.getlist("transaction_uuids")
        transaction_uuids_ancien_fedow = request.POST.getlist(
            "transaction_uuids_ancien_fedow"
        )
        uuid_pv = request.POST.get("uuid_pv", "")

        aucune_transaction_postee = not transaction_uuids and not transaction_uuids_ancien_fedow
        if aucune_transaction_postee or not uuid_pv:
            return render(
                request,
                "laboutik/partial/hx_print_feedback.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Parametres manquants."),
                },
            )

        printer_de_ce_terminal = imprimante_du_terminal(request.user)
        if printer_de_ce_terminal is None:
            return render(
                request,
                "laboutik/partial/hx_print_feedback.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Pas d'imprimante configurée sur ce terminal."),
                },
            )

        transactions_locales = list(
            Transaction.objects.filter(
                uuid__in=transaction_uuids,
                action=Transaction.REFUND,
            ).select_related("asset")
        )

        try:
            transactions_ancien_fedow = _relire_les_transactions_de_l_ancien_fedow(
                transaction_uuids_ancien_fedow
            )
        except Exception as erreur_ancien_fedow:
            logger.warning(
                f"Reçu de vidage non imprimé : l'ancien Fedow n'a pas pu relire les "
                f"transactions : {erreur_ancien_fedow}"
            )
            return render(
                request,
                "laboutik/partial/hx_print_feedback.html",
                {
                    "msg_type": "warning",
                    "msg_content": _(
                        "L'ancien Fedow ne répond pas : le reçu n'est pas imprimé. "
                        "Réessayez plus tard."
                    ),
                },
            )

        from laboutik.printing.formatters import formatter_recu_vider_carte
        from laboutik.printing.tasks import imprimer_async

        recu_data = formatter_recu_vider_carte(
            transactions_locales,
            transactions_ancien_fedow,
        )
        imprimer_async.delay(
            str(printer_de_ce_terminal.pk),
            recu_data,
            connection.schema_name,
        )
        return render(
            request,
            "laboutik/partial/hx_print_feedback.html",
            {
                "msg_type": "success",
                "msg_content": _("Reçu imprimé"),
            },
        )

    # ------------------------------------------------------------------ #
    #  Impression ticket de vente (bouton sur l'ecran de succes)           #
    #  Sale receipt printing (button on the success screen)                #
    # ------------------------------------------------------------------ #

    @action(
        detail=False,
        methods=["post"],
        url_path="imprimer_ticket",
        url_name="imprimer_ticket",
    )
    def imprimer_ticket(self, request):
        """
        POST /laboutik/paiement/imprimer_ticket/
        Imprime (ou re-imprime) le ticket d'une VENTE.
        / Prints (or reprints) the receipt of a SALE.

        LOCALISATION : laboutik/views.py

        FLUX :
        1. La vente : `uuid_vente` (bouton « Ré-imprimer » du detail d'une vente,
           bouton « Imprimer » de l'ecran de fin de paiement). Seule une vente ou un
           avoir regle, fait sur un point de vente, s'imprime
           (`vente_imprimable_a_la_caisse`).
        2. L'imprimante du terminal qui demande (`imprimante_du_terminal`).
        3. Le ticket : `formatter_ticket_vente(vente, operateur)`.
        4. L'impression part en tache Celery. Le journal des impressions compte les
           impressions de la VENTE (`impression_meta["uuid_transaction"]` = uuid de
           la vente, laboutik/printing/tasks.py) : la deuxieme est un DUPLICATA.
        5. Retourne un partial HTML de confirmation.
        / The sale, the terminal's printer, the receipt, the print task; the print
          log counts the SALE's prints: the second one is a DUPLICATE.
        """
        contexte_donnees_manquantes = {
            "msg_type": "warning",
            "msg_content": _("Donnees manquantes pour l'impression"),
        }

        vente = None
        uuid_de_la_vente_recu = request.POST.get("uuid_vente", "")
        try:
            vente = (
                Vente.objects.select_related("point_de_vente")
                .prefetch_related("reglements")
                .filter(uuid=uuid_module.UUID(uuid_de_la_vente_recu))
                .first()
            )
        except ValueError:
            vente = None

        if vente is None or not vente_imprimable_a_la_caisse(vente):
            return render(
                request,
                "laboutik/partial/hx_print_feedback.html",
                contexte_donnees_manquantes,
            )

        printer_de_ce_terminal = imprimante_du_terminal(request.user)
        if printer_de_ce_terminal is None:
            return render(
                request,
                "laboutik/partial/hx_print_feedback.html",
                {
                    "msg_type": "warning",
                    "msg_content": _(
                        "Aucune imprimante configurée pour ce terminal"
                    ),
                },
            )

        # Construire le ticket et lancer l'impression async
        # / Build the ticket and launch async printing
        from laboutik.printing.formatters import formatter_ticket_vente
        from laboutik.printing.tasks import imprimer_async

        # Operateur = user connecte (admin session)
        # / Operator = logged-in user (admin session)
        operateur = request.user if request.user.is_authenticated else None

        ticket_data = formatter_ticket_vente(vente, operateur)

        # Les metadonnees d'impression pour la tracabilite (LNE exigence 9). Le
        # champ `uuid_transaction` du journal recoit l'uuid de la VENTE : les
        # impressions se comptent par vente.
        # / Print metadata (LNE req. 9); the log's uuid_transaction gets the SALE uuid.
        ticket_data["impression_meta"] = {
            "uuid_transaction": str(vente.uuid),
            "cloture_uuid": None,
            "type_justificatif": "VENTE",
            "operateur_pk": str(operateur.pk) if operateur else None,
            "format_emission": "P",
        }

        imprimer_async.delay(
            str(printer_de_ce_terminal.pk),
            ticket_data,
            connection.schema_name,
        )

        # return render(request, "laboutik/partial/hx_print_confirmation.html")
        return render(
                request,
                "laboutik/partial/hx_print_feedback.html",
                {
                    "msg_type": "success",
                    "msg_content": _("Impression lancée"),
                },
            )

    # ----------------------------------------------------------------------- #
    #  Correction de moyen de paiement (conformite LNE exigence 4)             #
    #  Payment method correction (LNE compliance requirement 4)                #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["get"],
        url_path="formulaire_correction",
        url_name="formulaire_correction",
    )
    def formulaire_correction(self, request):
        """
        GET /laboutik/paiement/formulaire_correction/?ligne_uuid=...
        Affiche le formulaire de correction de moyen de paiement.
        / Shows the payment method correction form.

        LOCALISATION : laboutik/views.py
        """
        ligne_uuid = request.GET.get("ligne_uuid")
        if not ligne_uuid:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Ligne d'article introuvable"),
                },
                status=400,
            )

        # Un uuid illisible leve `ValidationError` (champ UUID de Django) : 404 aussi.
        # / An unreadable uuid raises ValidationError: 404 too.
        try:
            ligne = LigneArticle.objects.get(uuid=ligne_uuid)
        except (LigneArticle.DoesNotExist, ValueError, DjangoValidationError):
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Ligne d'article introuvable"),
                },
                status=404,
            )

        # La meme regle que la route : une ligne que la route refuserait n'ouvre pas
        # de formulaire (le message de refus est rendu tel quel).
        # / Same rule as the route: a line the route would refuse opens no form.
        raison_du_refus = raison_du_refus_de_correction(ligne)
        if raison_du_refus is not None:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {"msg_type": "warning", "msg_content": raison_du_refus},
                status=400,
            )

        # Les nouveaux moyens possibles (especes, CB, cheque), sans le moyen actuel,
        # par leur nom unique.
        # / The possible new methods, without the current one, by their single name.
        moyens_corrigeables = []
        for moyen_corrigeable in MOYENS_CORRIGEABLES_A_LA_CAISSE:
            if moyen_corrigeable != ligne.payment_method:
                moyens_corrigeables.append(
                    {
                        "code": moyen_corrigeable,
                        "label": nom_du_moyen_de_paiement(moyen_corrigeable),
                    }
                )

        # Le montant affiche est celui que la route deplacera : la somme des nets
        # vendus des lignes que la correction deplace (meme vente, meme moyen
        # actuel). Une seule definition, `lignes_que_la_correction_deplace`.
        # / The amount shown is what the route will move: the same lines.
        montant_que_la_correction_deplace = 0
        lignes_deplacees = lignes_que_la_correction_deplace(ligne)
        for ligne_deplacee in lignes_deplacees:
            montant_que_la_correction_deplace += ligne_deplacee.total_ttc

        context = {
            "ligne": ligne,
            "moyens_corrigeables": moyens_corrigeables,
            "moyen_actuel_label": nom_du_moyen_de_paiement(ligne.payment_method),
            "montant_du_reglement_a_la_francaise": euros_a_la_francaise(
                montant_que_la_correction_deplace
            ),
        }
        return render(
            request, "laboutik/partial/hx_corriger_moyen_paiement.html", context
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="corriger_moyen_paiement",
        url_name="corriger_moyen_paiement",
    )
    def corriger_moyen_paiement(self, request):
        """
        POST /laboutik/paiement/corriger_moyen_paiement/
        Corrige le moyen de paiement d'une LigneArticle existante.
        Cree une trace d'audit CorrectionPaiement (conformite LNE exigence 4).
        Le HMAC chain est casse volontairement — CorrectionPaiement sert de preuve.
        / Corrects the payment method of an existing LigneArticle.
        Creates a CorrectionPaiement audit trail (LNE compliance req. 4).
        The HMAC chain is intentionally broken — CorrectionPaiement serves as proof.

        LOCALISATION : laboutik/views.py

        Gardes de securite / Security guards (memes etiquettes que dans le code),
        toutes relues SOUS LE VERROU de la vente d'origine (`select_for_update`) :
        - Serializer : UUID valide, nouveau moyen dans ESP/CB/CHQ, raison, moyen vu
          par le caissier (`ancien_moyen`, champ cache du formulaire).
        - GARDE 1 : la ligne elle-meme (`raison_du_refus_de_correction`) — ancien
          moyen especes, CB ou cheque ; vente de la caisse ; vente reglee ; vente pas
          couverte par une cloture journaliere.
        - GARDE 2 : la ligne a change depuis l'ouverture du formulaire (moyen actuel
          different de `ancien_moyen`) — deux envois identiques ne font qu'une
          correction.
        - GARDE 3 : meme moyen interdit — pas de correction sans changement.
        - GARDE 4 : montant nul interdit — rien a deplacer.
        Un refus est rendu dans la zone du formulaire (`HX-Retarget`), pas a la
        place du detail.

        LES LIGNES DEPLACEES : `lignes_que_la_correction_deplace` (meme vente, meme
        moyen actuel), la meme fonction que l'ecran du formulaire : le montant affiche
        est le montant deplace. Une vente deja corrigee se corrige encore (CB → cheque
        apres especes → CB) : ses lignes portent le moyen actuel.
        Apres la correction, le detail de la vente d'origine est re-rendu.
        / The moved lines: the same function as the form screen. A corrected sale can
          be corrected again. The original sale's detail is re-rendered.

        VENTE DE CORRECTION (D14, CHANTIER-05-montants-entiers.md) :
        La vente d'origine est deja encaissee : elle ne change jamais. Dans la meme
        transaction que la correction des lignes, la caisse ecrit une vente CORRECTION,
        liee a la vente d'origine, sans article, avec deux reglements qui s'annulent :
        −montant a l'ancien moyen, +montant au nouveau. Le montant est la somme des
        `total_ttc` des lignes corrigees. `encaisser_vente` vient en dernier (numero,
        empreinte chainee).
        / The settled original sale never changes. In the same transaction, a CORRECTION
        sale linked to it, without items, with two payments that cancel out.
        """
        # --- Validation des champs via serializer DRF ---
        # Le serializer valide le format UUID, les choix de moyen, et la raison.
        # Les gardes metier (GARDE 1 a 4) restent dans la vue : elles dependent de
        # l'etat en base, relu sous verrou.
        # / Field validation via DRF serializer. Business guards (1 to 4) depend on
        # database state, read under lock.
        from laboutik.serializers import CorrectionPaiementSerializer

        serializer = CorrectionPaiementSerializer(data=request.POST)
        if not serializer.is_valid():
            premiere_erreur = list(serializer.errors.values())[0][0]
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": str(premiere_erreur),
                },
                status=400,
            )

        ligne_uuid = serializer.validated_data["ligne_uuid"]
        nouveau_moyen = serializer.validated_data["nouveau_moyen"]
        raison = serializer.validated_data["raison"]
        ancien_moyen_vu_par_le_caissier = serializer.validated_data["ancien_moyen"]

        # --- Recuperer la ligne d'article ---
        # / Get the article line
        ligne_cliquee = LigneArticle.objects.filter(uuid=ligne_uuid).first()
        if ligne_cliquee is None:
            return _refus_de_correction(
                request, _("Ligne d'article introuvable"), ligne_uuid, status=404
            )

        operateur = request.user if request.user.is_authenticated else None
        nombre_lignes_corrigees = 0

        # --- Tout se joue sous le verrou de la vente d'origine ---
        # Deux envois du meme formulaire (double clic, deux caisses) passent l'un
        # apres l'autre : le second relit la ligne APRES la premiere correction, et
        # ses gardes la refusent. Les gardes, la lecture des lignes et l'ecriture
        # sont dans la meme transaction.
        # / Everything happens under the original sale's lock: a second submission
        #   re-reads the line after the first correction and is refused.
        with db_transaction.atomic():
            if ligne_cliquee.vente_id is not None:
                Vente.objects.select_for_update().filter(
                    pk=ligne_cliquee.vente_id
                ).first()
            ligne = LigneArticle.objects.select_related("vente").get(
                pk=ligne_cliquee.pk
            )

            # --- GARDE 1 : la ligne elle-meme ---
            # Moyen corrigeable, vente de la caisse, vente reglee, pas couverte par
            # une cloture journaliere : `raison_du_refus_de_correction`, partagee
            # avec l'ecran du detail d'une vente et le formulaire.
            # / GUARD 1: the line itself, shared with the detail screen and the form.
            raison_du_refus = raison_du_refus_de_correction(ligne)
            if raison_du_refus is not None:
                return _refus_de_correction(request, raison_du_refus, ligne_uuid)

            # --- GARDE 2 : la ligne a change depuis l'ouverture du formulaire ---
            # Le formulaire envoie le moyen qu'il a affiche. Si le moyen actuel n'est
            # plus celui-la, une autre correction est passee entre-temps : refus.
            # / GUARD 2: the line changed since the form was opened: refused.
            ligne_deja_corrigee = ancien_moyen_vu_par_le_caissier != ligne.payment_method
            if ligne_deja_corrigee:
                return _refus_de_correction(
                    request,
                    _(
                        "Ce paiement vient d'être corrigé (moyen actuel : %(moyen)s). "
                        "Rouvrez la vente pour le corriger à nouveau."
                    )
                    % {"moyen": nom_du_moyen_de_paiement(ligne.payment_method)},
                    ligne_uuid,
                )

            # --- GARDE 3 : meme moyen = pas de correction ---
            # / GUARD 3: same method = no correction needed
            if ligne.payment_method == nouveau_moyen:
                return _refus_de_correction(
                    request, _("Le moyen de paiement est deja identique"), ligne_uuid
                )

            # --- Les lignes que la correction deplace ---
            # Toutes les lignes de la vente qui portent le moyen actuel de la ligne :
            # la meme fonction que l'ecran du formulaire, qui en a affiche la somme.
            # La garde 1 a refuse une ligne sans vente reglee : la vente existe ici.
            # / The lines the correction moves: the same function as the form screen.
            ancien_moyen = ligne.payment_method
            lignes_a_corriger = lignes_que_la_correction_deplace(ligne)
            vente_d_origine = ligne.vente

            # Le montant corrige : la somme des nets vendus des lignes, des entiers
            # figes a la vente, additionnes (jamais recalcules).
            # / The corrected amount: the sum of the lines' frozen net totals.
            montant_corrige_en_centimes = 0
            for ligne_a_corriger in lignes_a_corriger:
                montant_corrige_en_centimes += ligne_a_corriger.total_ttc

            # --- GARDE 4 : une vente dont les lignes corrigees valent 0 ---
            # Il n'y a pas d'argent a deplacer : la vente CORRECTION n'aurait que des
            # reglements de 0, que le service de vente refuse. Refus propre, rien
            # n'est ecrit.
            # / GUARD 4: lines worth 0, nothing to move: clean refusal.
            if montant_corrige_en_centimes == 0:
                return _refus_de_correction(
                    request, _("Rien à corriger : le montant est nul."), ligne_uuid
                )

            # --- Les traces d'audit, le nouveau moyen et la vente de correction ---
            # Une CorrectionPaiement par LigneArticle pour la tracabilite.
            # / Audit trails, new method and the correction sale.
            for ligne_a_corriger in lignes_a_corriger:
                CorrectionPaiement.objects.create(
                    ligne_article=ligne_a_corriger,
                    ancien_moyen=ancien_moyen,
                    nouveau_moyen=nouveau_moyen,
                    raison=raison,
                    operateur=operateur,
                )
                # Le moyen de la ligne change : son empreinte par ligne ne correspond
                # plus, c'est attendu. La preuve de la correction est la trace
                # CorrectionPaiement et la vente CORRECTION ci-dessous, scellee dans
                # la chaine des ventes.
                # / The line's method changes: its per-line fingerprint no longer
                # matches, as expected. The proof is the trace and the CORRECTION sale.
                ligne_a_corriger.payment_method = nouveau_moyen
                ligne_a_corriger.save(update_fields=["payment_method"])
                nombre_lignes_corrigees += 1

            # La vente CORRECTION : liee a la vente d'origine, sans article, au point de
            # vente de la vente d'origine (le formulaire n'en envoie pas), a l'operateur
            # de la correction.
            # / The CORRECTION sale: linked, without items, at the original sale's
            # point of sale, by the correction's operator.
            vente_de_correction = ouvrir_vente(
                origine=SaleOrigin.LABOUTIK,
                nature=Vente.Nature.CORRECTION,
                point_de_vente=vente_d_origine.point_de_vente,
                operateur=operateur,
                vente_liee=vente_d_origine,
            )
            # Deux reglements qui s'annulent : l'argent quitte l'ancien moyen et
            # arrive sur le nouveau.
            # / Two payments that cancel out: from the old method to the new one.
            ajouter_reglement(
                vente_de_correction,
                moyen=ancien_moyen,
                montant=-montant_corrige_en_centimes,
            )
            ajouter_reglement(
                vente_de_correction,
                moyen=nouveau_moyen,
                montant=montant_corrige_en_centimes,
            )
            # En dernier : les egalites, le numero et l'empreinte chainee.
            # / Last: equalities, number and chained fingerprint.
            encaisser_vente(vente_de_correction)

        logger.info(
            f"Correction paiement : {nombre_lignes_corrigees} ligne(s) "
            f"{ancien_moyen} → {nouveau_moyen} "
            f"par {request.user} — raison : {raison}"
        )

        # Le detail de la vente d'origine est re-rendu (il remplace l'ancien sous la
        # ligne de la liste) : le bouton « Corriger » suit le nouveau moyen, la vente
        # CORRECTION apparait dans les ventes derivees, et un message dit la
        # correction faite.
        # / The original sale's detail is re-rendered, with a confirmation message.
        vente_d_origine_relue = (
            Vente.objects.select_related("point_de_vente", "vente_liee")
            .prefetch_related("ventes_derivees", "reglements")
            .get(pk=vente_d_origine.pk)
        )
        context = _contexte_du_detail_d_une_vente(vente_d_origine_relue)
        context["correction_faite"] = {
            "ancien_moyen_label": nom_du_moyen_de_paiement(ancien_moyen),
            "nouveau_moyen_label": nom_du_moyen_de_paiement(nouveau_moyen),
        }
        return render(request, "laboutik/partial/hx_detail_vente.html", context)


# --------------------------------------------------------------------------- #
#  CommandeViewSet — commandes de restaurant (Phase 4)                        #
#  CommandeViewSet — restaurant orders (Phase 4)                              #
# --------------------------------------------------------------------------- #


class CommandeViewSet(viewsets.ViewSet):
    """
    Gestion des commandes de restaurant (mode table).
    Restaurant order management (table mode).

    LOCALISATION : laboutik/views.py

    Flux / Flow :
    1. ouvrir_commande()    → crée une commande pour une table / creates order for a table
    2. ajouter_articles()   → ajoute des articles a une commande OPEN / adds articles to an OPEN order
    3. marquer_servie()     → passe la commande en SERVED / marks order as SERVED
    4. payer_commande()     → réutilise les méthodes de paiement existantes / reuses existing payment methods
    5. annuler_commande()   → annule la commande / cancels the order
    """

    permission_classes = [HasLaBoutikTerminalAccess]

    # ----------------------------------------------------------------------- #
    #  1. Ouvrir une commande                                                  #
    #  1. Open an order                                                        #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["post"], url_path="ouvrir", url_name="ouvrir")
    def ouvrir_commande(self, request):
        """
        POST /laboutik/commande/ouvrir/
        Crée une nouvelle commande pour une table.
        Creates a new order for a table.

        Corps attendu (JSON) / Expected body (JSON) :
        {
            "table_uuid": "uuid-de-la-table",
            "uuid_pv": "uuid-du-point-de-vente",
            "articles": [
                {"product_uuid": "...", "price_uuid": "...", "qty": 2},
                ...
            ]
        }
        """
        serializer = CommandeSerializer(data=request.data)
        if not serializer.is_valid():
            premiere_erreur = next(iter(serializer.errors.values()))
            if isinstance(premiere_erreur, list):
                premiere_erreur = premiere_erreur[0]
            context_erreur = {
                "msg_type": "warning",
                "msg_content": str(premiere_erreur),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        donnees = serializer.validated_data
        table_uuid = donnees.get("table_uuid")
        uuid_pv = donnees["uuid_pv"]
        articles_data = donnees["articles"]

        # Charger le point de vente
        # Load the point of sale
        try:
            point_de_vente = PointDeVente.objects.get(uuid=uuid_pv)
        except PointDeVente.DoesNotExist:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Point de vente introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=404
            )

        # Charger la table (si fournie)
        # Load the table (if provided)
        table_obj = None
        if table_uuid is not None:
            try:
                table_obj = Table.objects.get(uuid=table_uuid)
            except Table.DoesNotExist:
                context_erreur = {
                    "msg_type": "warning",
                    "msg_content": _("Table introuvable"),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request,
                    "laboutik/partial/hx_messages.html",
                    context_erreur,
                    status=404,
                )

        # Charger les produits autorisés du PV (en une seule requête)
        # Load authorized PV products (single query)
        produits_autorises = {
            str(p.uuid): p
            for p in point_de_vente.products.filter(methode_caisse__isnull=False)
        }

        # Préparer les articles validés
        # Prepare validated articles
        articles_valides = []
        for article_data in articles_data:
            product_uuid_str = str(article_data["product_uuid"])
            produit = produits_autorises.get(product_uuid_str)
            if produit is None:
                logger.warning(
                    f"ouvrir_commande: produit {product_uuid_str} non autorisé dans PV {point_de_vente.name}"
                )
                continue

            try:
                prix = Price.objects.get(
                    uuid=article_data["price_uuid"], product=produit
                )
            except Price.DoesNotExist:
                logger.warning(
                    f"ouvrir_commande: prix {article_data['price_uuid']} non trouvé pour {produit.name}"
                )
                continue

            # Un tarif en points se paie par la carte du client, au comptoir :
            # une commande de table ne sait pas l'encaisser.
            # / A points price is paid by card at the counter, never via an order.
            if _tarif_est_en_points(prix):
                context_erreur = {
                    "msg_type": "warning",
                    "msg_content": _(
                        "Un tarif en points ou en temps ne passe pas par une "
                        "commande de table : encaissez-le au comptoir."
                    ),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request,
                    "laboutik/partial/hx_messages.html",
                    context_erreur,
                    status=400,
                )

            articles_valides.append(
                {
                    "product": produit,
                    "price": prix,
                    "qty": article_data["qty"],
                }
            )

        if not articles_valides:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Aucun article valide dans la commande"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # Bloc atomique : table → commande → articles
        # Atomic block: table → order → articles
        with db_transaction.atomic():
            # Marquer la table comme occupée
            # Mark table as occupied
            if table_obj is not None:
                table_obj.statut = Table.OCCUPEE
                table_obj.save(update_fields=["statut"])

            # Créer la commande
            # Create the order
            commande = CommandeSauvegarde.objects.create(
                table=table_obj,
                statut=CommandeSauvegarde.OPEN,
                responsable=request.user if request.user.is_authenticated else None,
                commentaire="",
            )

            # Créer les articles de la commande
            # Create order articles
            for article in articles_valides:
                prix_centimes = int(round(article["price"].prix * 100))
                ArticleCommandeSauvegarde.objects.create(
                    commande=commande,
                    product=article["product"],
                    price=article["price"],
                    qty=article["qty"],
                    reste_a_payer=prix_centimes * article["qty"],
                    reste_a_servir=article["qty"],
                    statut=ArticleCommandeSauvegarde.EN_ATTENTE,
                )

        context = {
            "msg_type": "success",
            "msg_content": _("Commande créée"),
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context, status=201)

    # ----------------------------------------------------------------------- #
    #  2. Ajouter des articles à une commande existante                        #
    #  2. Add articles to an existing order                                    #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["post"],
        url_path="ajouter/(?P<commande_uuid>[^/.]+)",
        url_name="ajouter",
    )
    def ajouter_articles(self, request, commande_uuid=None):
        """
        POST /laboutik/commande/ajouter/<commande_uuid>/
        Ajoute des articles a une commande OPEN existante.
        Adds articles to an existing OPEN order.
        """
        # Charger la commande
        # Load the order
        try:
            commande = CommandeSauvegarde.objects.get(uuid=commande_uuid)
        except (CommandeSauvegarde.DoesNotExist, ValueError):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Commande introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=404
            )

        # Vérifier que la commande est encore ouverte
        # Check that the order is still open
        if commande.statut != CommandeSauvegarde.OPEN:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Cette commande n'est plus ouverte"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # Valider les articles
        # Validate articles
        serializer = ArticleCommandeSerializer(data=request.data, many=True)
        if not serializer.is_valid():
            premiere_erreur = next(iter(serializer.errors))
            context_erreur = {
                "msg_type": "warning",
                "msg_content": str(premiere_erreur),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        articles_data = serializer.validated_data

        if not articles_data:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Aucun article fourni"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # Un tarif en points se paie par la carte du client, au comptoir : une
        # commande de table ne sait pas l'encaisser. Refus AVANT toute ecriture.
        # / A points price is never added to an order: refused before any write.
        uuids_des_tarifs_demandes = []
        for article_data in articles_data:
            uuids_des_tarifs_demandes.append(article_data["price_uuid"])
        un_tarif_est_en_points = Price.objects.filter(
            Q(asset__isnull=False) | Q(non_fiduciaire=True),
            uuid__in=uuids_des_tarifs_demandes,
        ).exists()
        if un_tarif_est_en_points:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _(
                    "Un tarif en points ou en temps ne passe pas par une "
                    "commande de table : encaissez-le au comptoir."
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # Créer les articles dans un bloc atomique
        # Create articles in an atomic block
        with db_transaction.atomic():
            for article_data in articles_data:
                try:
                    produit = Product.objects.get(uuid=article_data["product_uuid"])
                    prix = Price.objects.get(
                        uuid=article_data["price_uuid"], product=produit
                    )
                except (Product.DoesNotExist, Price.DoesNotExist):
                    continue

                prix_centimes = int(round(prix.prix * 100))
                ArticleCommandeSauvegarde.objects.create(
                    commande=commande,
                    product=produit,
                    price=prix,
                    qty=article_data["qty"],
                    reste_a_payer=prix_centimes * article_data["qty"],
                    reste_a_servir=article_data["qty"],
                    statut=ArticleCommandeSauvegarde.EN_ATTENTE,
                )

        context = {
            "msg_type": "success",
            "msg_content": _("Articles ajoutés"),
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context)

    # ----------------------------------------------------------------------- #
    #  3. Marquer une commande comme servie                                    #
    #  3. Mark an order as served                                              #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["post"],
        url_path="servir/(?P<commande_uuid>[^/.]+)",
        url_name="servir",
    )
    def marquer_servie(self, request, commande_uuid=None):
        """
        POST /laboutik/commande/servir/<commande_uuid>/
        Passe la commande en SERVED et ses articles PRET en SERVI.
        Marks the order as SERVED and its READY articles as SERVED.
        """
        try:
            commande = CommandeSauvegarde.objects.get(uuid=commande_uuid)
        except (CommandeSauvegarde.DoesNotExist, ValueError):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Commande introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=404
            )

        if commande.statut not in (CommandeSauvegarde.OPEN, CommandeSauvegarde.SERVED):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _(
                    "Cette commande ne peut pas être marquée comme servie"
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        with db_transaction.atomic():
            # Marquer les articles PRET ou EN_ATTENTE comme SERVI
            # Mark READY or WAITING articles as SERVED
            commande.articles.filter(
                statut__in=[
                    ArticleCommandeSauvegarde.PRET,
                    ArticleCommandeSauvegarde.EN_ATTENTE,
                    ArticleCommandeSauvegarde.EN_COURS,
                ],
            ).update(
                statut=ArticleCommandeSauvegarde.SERVI,
                reste_a_servir=0,
            )

            commande.statut = CommandeSauvegarde.SERVED
            commande.save(update_fields=["statut"])

            # Mettre à jour le statut de la table
            # Update table status
            if commande.table is not None:
                commande.table.statut = Table.SERVIE
                commande.table.save(update_fields=["statut"])

        context = {
            "msg_type": "success",
            "msg_content": _("Commande servie"),
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context)

    # ----------------------------------------------------------------------- #
    #  4. Payer une commande                                                   #
    #  4. Pay for an order                                                     #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["post"],
        url_path="payer/(?P<commande_uuid>[^/.]+)",
        url_name="payer",
    )
    def payer_commande(self, request, commande_uuid=None):
        """
        POST /laboutik/commande/payer/<commande_uuid>/
        Paie la commande en réutilisant le flux de paiement existant.
        Pays the order by reusing the existing payment flow.

        Corps attendu (POST form) / Expected body (POST form) :
        - moyen_paiement : code du moyen ("espece", "carte_bancaire", "CH", "nfc")
        - uuid_pv : UUID du point de vente
        - given_sum : somme donnée (espèces, optionnel)
        - tag_id : tag NFC du client (cashless, optionnel)

        Les articles sont chargés depuis la commande (pas du POST).
        Articles are loaded from the order (not from POST).
        """
        try:
            commande = CommandeSauvegarde.objects.select_related("table").get(
                uuid=commande_uuid
            )
        except (CommandeSauvegarde.DoesNotExist, ValueError):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Commande introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=404
            )

        if commande.statut not in (CommandeSauvegarde.OPEN, CommandeSauvegarde.SERVED):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Cette commande ne peut pas être payée"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        # Charger le PV
        # Load the PV
        uuid_pv = request.POST.get("uuid_pv")
        try:
            point_de_vente = PointDeVente.objects.get(uuid=uuid_pv)
        except (PointDeVente.DoesNotExist, ValueError):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Point de vente introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=404
            )

        # Construire articles_panier depuis les articles de la commande
        # Build articles_panier from order articles
        articles_commande = commande.articles.filter(
            statut__in=[
                ArticleCommandeSauvegarde.EN_ATTENTE,
                ArticleCommandeSauvegarde.EN_COURS,
                ArticleCommandeSauvegarde.PRET,
                ArticleCommandeSauvegarde.SERVI,
            ],
        ).select_related("product", "price")

        articles_panier = []
        for article_cmd in articles_commande:
            prix_centimes = int(round(article_cmd.price.prix * 100))
            articles_panier.append(
                {
                    "product": article_cmd.product,
                    "price": article_cmd.price,
                    "quantite": article_cmd.qty,
                    "prix_centimes": prix_centimes,
                }
            )

        # Un retour de consigne ne se règle pas depuis une commande de table.
        # Ce chemin construit son propre panier et appelle directement les flux de
        # paiement : les gardes de `payer()` ne s'y appliquent pas. Or la cascade de
        # débit NFC s'arrête sans rien écrire sur un montant négatif — le caissier
        # verrait un écran de succès sans qu'aucune ligne ni aucun crédit n'existe — et
        # un règlement en carte ou en chèque produirait une ligne négative estampillée
        # d'un moyen qu'on ne rembourse pas.
        # / A deposit return is not settled from a table order: this path builds its own
        #   cart and bypasses payer()'s guards, where the NFC cascade would show success
        #   without writing anything.
        if _panier_contient_retour_consigne(articles_panier):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _(
                    "Un retour de consigne se règle au comptoir, pas depuis une commande."
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                context_erreur,
                status=400,
            )

        # Filet de securite : une commande ne contient jamais de tarif en points
        # (ouvrir_commande et ajouter_articles les refusent). Si une commande en
        # contient quand meme, elle ne se paie pas : ce chemin appelle les flux
        # de paiement sans passer par les gardes de `payer()`.
        # / Safety net: an order never holds a points price; if it does, refused.
        if _panier_est_en_points(articles_panier):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _(
                    "Un tarif en points ou en temps ne passe pas par une "
                    "commande de table : encaissez-le au comptoir."
                ),
                "selector_bt_retour": "#messages",
            }
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                context_erreur,
                status=400,
            )

        if not articles_panier:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Aucun article à payer dans cette commande"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        total_centimes = _calculer_total_panier_centimes(articles_panier)
        total_en_euros = total_centimes / 100

        state = _construire_state(point_de_vente, user=request.user)

        donnees_paiement = request.POST.dict()
        donnees_paiement["total"] = total_centimes
        somme_donnee_brute = donnees_paiement.get("given_sum", "")
        if somme_donnee_brute == "":
            donnees_paiement["given_sum"] = 0
        else:
            # Le JS envoie « somme en euros x 100 ». Ce calcul peut donner
            # un nombre a virgule (ex : 329.99999999999994). int() planterait :
            # on arrondit d'abord, comme dans payer_complementaire.
            # / The JS sends "euros x 100", which can be a float: round first.
            try:
                donnees_paiement["given_sum"] = int(round(float(somme_donnee_brute)))
            except (ValueError, TypeError):
                donnees_paiement["given_sum"] = 0
        donnees_paiement["missing"] = 0

        moyen_paiement_code = donnees_paiement.get("moyen_paiement", "")
        logger.info(
            f"payer_commande: commande={commande_uuid}, moyen={moyen_paiement_code}, "
            f"total={total_centimes}cts, articles={len(articles_panier)}"
        )

        # Liste blanche des moyens d'une commande de table. Le moyen poste est
        # transmis tel quel aux fonctions de paiement : sans cette garde, un POST
        # « gift » enregistrerait la commande comme offerte, sans mode gerant.
        # / Allowed methods for a table order: the posted method is passed as-is
        #   to the payment functions; without this guard a "gift" POST would
        #   record the order as gifted.
        moyens_autorises_pour_une_commande = ("nfc", "espece", "carte_bancaire", "CH")
        if moyen_paiement_code not in moyens_autorises_pour_une_commande:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Moyen de paiement non accepte pour une commande"),
                    "selector_bt_retour": "#messages",
                },
                status=400,
            )

        # --- Aiguillage NFC / non-NFC ---
        # --- NFC / non-NFC routing ---
        #
        # NFC : _payer_par_nfc() a son propre bloc atomic (savepoint imbriqué).
        #   On l'appelle dans un bloc atomic externe pour garantir l'atomicité
        #   entre le paiement fedow_core et la mise à jour de la commande/table.
        #   Détection du succès : on cherche 'paiement-succes' dans le HTML retourné.
        #   render() retourne HttpResponse (pas TemplateResponse), donc template_name
        #   n'est pas disponible — on utilise le contenu HTML directement.
        # NFC: _payer_par_nfc() has its own atomic block (nested savepoint).
        #   We wrap it in an outer atomic to guarantee atomicity between
        #   the fedow_core payment and the order/table update.
        #   Success detection: we look for 'paiement-succes' in the returned HTML.

        # L'identifiant du paiement : posé sur chaque ligne, et clé d'idempotence de
        # la vente. En NFC, il est passé à `_payer_par_nfc`, qui écrit la vente sous
        # cette clé : c'est par elle que la commande retrouve sa vente.
        # / The payment id: set on every line, and the sale's idempotency key. In NFC,
        # passed to _payer_par_nfc; the order finds its sale through it.
        uuid_transaction = uuid_module.uuid4()

        if moyen_paiement_code == "nfc":
            with db_transaction.atomic():
                paiement_vs = PaiementViewSet()
                response_nfc = paiement_vs._payer_par_nfc(
                    request,
                    state,
                    donnees_paiement,
                    articles_panier,
                    total_en_euros,
                    total_centimes,
                    False,
                    moyen_paiement_code,
                    point_de_vente,
                    uuid_transaction_impose=uuid_transaction,
                )

                # Détecter le succès NFC via le data-testid dans le HTML
                # Detect NFC success via data-testid in the HTML
                nfc_paiement_reussi = b"paiement-succes" in response_nfc.content

                if not nfc_paiement_reussi:
                    # Fonds insuffisants, carte inconnue, etc.
                    # Le savepoint interne a déjà rollback.
                    # Insufficient funds, unknown card, etc.
                    # The inner savepoint already rolled back.
                    return response_nfc

                # La vente écrite par le paiement NFC, retrouvée par sa clé.
                # Une commande payée a TOUJOURS sa vente. Si elle est introuvable
                # après un succès, l'exception sort de ce bloc atomic : il annule le
                # paiement NFC et le statut de la commande, qui reste à payer.
                # / The sale written by the NFC payment, found by its key. A paid
                # order ALWAYS has its sale: if missing, the exception leaves this
                # atomic block, which rolls back the payment and the order status.
                vente_du_paiement_nfc = Vente.objects.filter(
                    idempotency_key=str(uuid_transaction),
                ).first()
                if vente_du_paiement_nfc is None:
                    raise RuntimeError(
                        f"payer_commande : paiement NFC réussi sans vente pour la clé "
                        f"{uuid_transaction} (commande {commande.uuid})"
                    )

                # NFC réussi → mettre à jour commande + table
                # NFC succeeded → update order + table
                commande.statut = CommandeSauvegarde.PAID
                commande.vente = vente_du_paiement_nfc
                commande.save(update_fields=["statut", "vente"])

                commande.articles.exclude(
                    statut=ArticleCommandeSauvegarde.ANNULE,
                ).update(
                    statut=ArticleCommandeSauvegarde.SERVI,
                    reste_a_payer=0,
                    reste_a_servir=0,
                )

                if commande.table is not None:
                    autres_commandes_ouvertes = (
                        CommandeSauvegarde.objects.filter(
                            table=commande.table,
                            statut__in=[
                                CommandeSauvegarde.OPEN,
                                CommandeSauvegarde.SERVED,
                            ],
                        )
                        .exclude(uuid=commande.uuid)
                        .exists()
                    )
                    if not autres_commandes_ouvertes:
                        commande.table.statut = Table.LIBRE
                        commande.table.save(update_fields=["statut"])

            return response_nfc

        # --- Paiement non-NFC (espèces, CB, chèque) ---
        # --- Non-NFC payment (cash, CC, check) ---
        with db_transaction.atomic():
            # La vente de la commande : ouverte en premier, encaissée avant le
            # changement de statut, dans la MÊME transaction que les lignes et la
            # commande. Pas de consigne (refusée plus haut), pas de carte client.
            # / The order's sale: opened first, settled before the status change,
            # in the SAME transaction as the lines and the order.
            vente = _ouvrir_la_vente_de_caisse(
                request,
                point_de_vente,
                uuid_transaction,
                consigne_dans_panier=False,
                carte_client=None,
                adherent=None,
            )

            _creer_lignes_articles(
                articles_panier,
                moyen_paiement_code,
                uuid_transaction=uuid_transaction,
                point_de_vente=point_de_vente,
                vente=vente,
            )

            # Un règlement du moyen, du montant encaissé, puis l'encaissement.
            # / One payment of the method, of the collected amount, then settle.
            _regler_et_encaisser_la_vente_de_caisse(
                vente, articles_panier, moyen_paiement_code
            )

            # Marquer la commande comme payée, avec sa vente
            # Mark order as paid, with its sale
            commande.statut = CommandeSauvegarde.PAID
            commande.vente = vente
            commande.save(update_fields=["statut", "vente"])

            # Marquer tous les articles comme servis
            # Mark all articles as served
            commande.articles.exclude(
                statut=ArticleCommandeSauvegarde.ANNULE,
            ).update(
                statut=ArticleCommandeSauvegarde.SERVI,
                reste_a_payer=0,
                reste_a_servir=0,
            )

            # Libérer la table si pas d'autre commande ouverte dessus
            # Free the table if no other open order on it
            if commande.table is not None:
                autres_commandes_ouvertes = (
                    CommandeSauvegarde.objects.filter(
                        table=commande.table,
                        statut__in=[CommandeSauvegarde.OPEN, CommandeSauvegarde.SERVED],
                    )
                    .exclude(uuid=commande.uuid)
                    .exists()
                )

                if not autres_commandes_ouvertes:
                    commande.table.statut = Table.LIBRE
                    commande.table.save(update_fields=["statut"])

        # Construire la réponse succès pour espèces/CB/chèque
        # Build success response for cash/CC/check
        donnees_paiement["give_back"] = 0
        if (
            moyen_paiement_code == "espece"
            and donnees_paiement["given_sum"] > total_centimes
        ):
            donnees_paiement["give_back"] = (
                donnees_paiement["given_sum"] - total_centimes
            ) / 100

        context = {
            "currency_data": CURRENCY_DATA,
            "payment": donnees_paiement,
            "monnaie_name": state["place"]["monnaie_name"],
            "moyen_paiement": PAYMENT_METHOD_TRANSLATIONS.get(moyen_paiement_code, ""),
            "deposit_is_present": False,
            "total": total_en_euros,
            "state": state,
            "original_payment": None,
        }
        return render(
            request, "laboutik/partial/hx_return_payment_success.html", context
        )

    # ----------------------------------------------------------------------- #
    #  5. Annuler une commande                                                 #
    #  5. Cancel an order                                                      #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["post"],
        url_path="annuler/(?P<commande_uuid>[^/.]+)",
        url_name="annuler",
    )
    def annuler_commande(self, request, commande_uuid=None):
        """
        POST /laboutik/commande/annuler/<commande_uuid>/
        Annule la commande et libère la table si nécessaire.
        Cancels the order and frees the table if needed.
        """
        try:
            commande = CommandeSauvegarde.objects.select_related("table").get(
                uuid=commande_uuid
            )
        except (CommandeSauvegarde.DoesNotExist, ValueError):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Commande introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=404
            )

        if commande.statut == CommandeSauvegarde.PAID:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Une commande payée ne peut pas être annulée"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        with db_transaction.atomic():
            # Annuler la commande et ses articles
            # Cancel the order and its articles
            commande.statut = CommandeSauvegarde.CANCEL
            commande.save(update_fields=["statut"])

            commande.articles.exclude(
                statut=ArticleCommandeSauvegarde.ANNULE,
            ).update(statut=ArticleCommandeSauvegarde.ANNULE)

            # Libérer la table si pas d'autre commande ouverte dessus
            # Free the table if no other open order on it
            if commande.table is not None:
                autres_commandes_ouvertes = (
                    CommandeSauvegarde.objects.filter(
                        table=commande.table,
                        statut__in=[CommandeSauvegarde.OPEN, CommandeSauvegarde.SERVED],
                    )
                    .exclude(uuid=commande.uuid)
                    .exists()
                )

                if not autres_commandes_ouvertes:
                    commande.table.statut = Table.LIBRE
                    commande.table.save(update_fields=["statut"])

        context = {
            "msg_type": "success",
            "msg_content": _("Commande annulée"),
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context)


class ArticlePanelViewSet(viewsets.ViewSet):
    """
    Panel contextuel article POS — menu d'actions + vue stock.
    Ouvert par un long press sur une tuile article.
    / Article context panel for POS — actions menu + stock view.
    Opened by a long press on an article tile.

    LOCALISATION : laboutik/views.py

    URLS :
        GET  /laboutik/article-panel/{product_uuid}/panel/  → menu principal
        GET  /laboutik/article-panel/{product_uuid}/stock/   → vue stock
        POST /laboutik/article-panel/{product_uuid}/stock/{action}/ → action stock

    TEMPLATES :
        laboutik/partial/article_panel.html       → menu principal
        laboutik/partial/article_panel_stock.html  → vue stock détaillée
    """

    permission_classes = [HasLaBoutikTerminalAccess]

    ACTIONS_AUTORISEES = ["reception", "perte", "ajustement"]

    # Mapping action URL → TypeMouvement / URL action → movement type mapping
    ACTION_TYPE_MAP = {
        "reception": TypeMouvement.RE,
        "perte": TypeMouvement.PE,
        "ajustement": TypeMouvement.AJ,
    }

    def panel(self, request, product_uuid):
        """
        GET — Menu principal du panel contextuel.
        / GET — Main menu of the context panel.
        """
        product = get_object_or_404(Product, uuid=product_uuid)
        stock = Stock.objects.filter(product=product).first()

        context = {
            "product": product,
            "has_stock": stock is not None,
        }
        return render(request, "laboutik/partial/article_panel.html", context)

    def stock_detail(self, request, product_uuid):
        """
        GET — Vue stock détaillée avec formulaire d'actions.
        / GET — Detailed stock view with action form.
        """
        product = get_object_or_404(Product, uuid=product_uuid)
        stock = get_object_or_404(Stock, product=product)
        context = _build_stock_context(product, stock)
        return render(request, "laboutik/partial/article_panel_stock.html", context)

    def stock_action(self, request, product_uuid, action):
        """
        POST — Exécute une action stock (reception/perte/ajustement).
        Retourne la vue stock mise à jour + header HX-Trigger.
        / POST — Execute a stock action. Returns updated stock view + HX-Trigger header.
        """
        # Valider l'action contre la whitelist / Validate action against whitelist
        if action not in self.ACTIONS_AUTORISEES:
            return HttpResponse("Action invalide", status=400)

        product = get_object_or_404(Product, uuid=product_uuid)
        stock = get_object_or_404(Stock, product=product)

        # L'ajustement utilise AjustementSerializer (stock_reel >= 0)
        # Les autres utilisent MouvementRapideSerializer (quantite >= 1)
        # / Adjustment uses AjustementSerializer (stock_reel >= 0)
        # Others use MouvementRapideSerializer (quantite >= 1)
        if action == "ajustement":
            from inventaire.serializers import AjustementSerializer

            # Le formulaire POS envoie "quantite" → on mappe vers "stock_reel"
            # / POS form sends "quantite" → map to "stock_reel"
            data_ajustement = {
                "stock_reel": request.POST.get("quantite", ""),
                "motif": request.POST.get("motif", ""),
            }
            serializer = AjustementSerializer(data=data_ajustement)
        else:
            serializer = MouvementRapideSerializer(data=request.POST)

        if not serializer.is_valid():
            messages_erreur = []
            for champ, erreurs in serializer.errors.items():
                for erreur in erreurs:
                    messages_erreur.append(str(erreur))
            erreur_feedback = " ".join(messages_erreur)

            context = _build_stock_context(
                product, stock, erreur_feedback=erreur_feedback
            )
            return render(request, "laboutik/partial/article_panel_stock.html", context)

        utilisateur = request.user if request.user.is_authenticated else None
        motif = serializer.validated_data.get("motif", "")

        if action == "ajustement":
            # Ajustement : stock_reel = stock réel compté, le service calcule le delta
            # / Adjustment: stock_reel = real counted stock, service computes delta
            StockService.ajuster_inventaire(
                stock=stock,
                stock_reel=serializer.validated_data["stock_reel"],
                motif=motif,
                utilisateur=utilisateur,
            )
        else:
            type_mouvement = self.ACTION_TYPE_MAP[action]
            StockService.creer_mouvement(
                stock=stock,
                type_mouvement=type_mouvement,
                quantite=serializer.validated_data["quantite"],
                motif=motif,
                utilisateur=utilisateur,
            )

        stock.refresh_from_db()

        # Pas de broadcast ici : StockService.creer_mouvement / ajuster_inventaire
        # préviennent déjà toutes les caisses (inventaire/services.py).
        # / No broadcast here: StockService already notifies all POS terminals.

        # Message de feedback / Feedback message
        label_action = {
            "reception": _("Réception"),
            "perte": _("Perte"),
            "ajustement": _("Ajustement"),
        }
        quantite_lisible = _formater_stock_lisible(stock.quantite, stock.unite)
        message = f"{label_action[action]} effectuée. Stock : {quantite_lisible}"

        context = _build_stock_context(product, stock, message_feedback=message)
        response = render(request, "laboutik/partial/article_panel_stock.html", context)
        response["HX-Trigger"] = "stockUpdated"
        return response

    def toggle_bloquant(self, request, product_uuid):
        """
        POST — Bascule autoriser_vente_hors_stock sur le stock.
        / POST — Toggle autoriser_vente_hors_stock on stock.
        """
        product = get_object_or_404(Product, uuid=product_uuid)
        stock = get_object_or_404(Stock, product=product)

        stock.autoriser_vente_hors_stock = not stock.autoriser_vente_hors_stock
        stock.save(update_fields=["autoriser_vente_hors_stock"])

        # Broadcast pour mettre à jour l'état bloquant sur les autres caisses
        # / Broadcast to update blocking state on other POS terminals
        broadcast_stock_update([donnees_badge_stock(stock)])

        etat_label = (
            _("autorisée") if stock.autoriser_vente_hors_stock else _("bloquée")
        )
        message = f"{_('Vente hors stock')} : {etat_label}"

        context = _build_stock_context(product, stock, message_feedback=message)
        response = render(request, "laboutik/partial/article_panel_stock.html", context)
        response["HX-Trigger"] = "stockUpdated"
        return response


class BridgeThrottle(AnonRateThrottle):
    """
    Anti-brute-force sur le bridge : 10 requêtes/minute par IP.
    / Brute-force protection on bridge: 10 req/min per IP.
    """

    rate = "10/min"
    scope = "laboutik_auth_bridge"


@method_decorator(csrf_exempt, name="dispatch")
class LaBoutikAuthBridgeView(APIView):
    """
    Pont d'authentification hardware : échange une clé API contre un cookie session.
    / Hardware auth bridge: trades an API key for a session cookie.

    LOCALISATION : laboutik/views.py

    Flux :
    1. Client POST un formulaire avec : api_key
    2. Validation de la clé (401 si invalide)
    3. Si la clé n'a pas de user lié (legacy
     V1) : 400
    4. Si user.is_active=False (révoqué) : 401
    5. django.contrib.auth.login() pose le cookie sessionid
    6. set_expiry(12h) — session courte par hygiène

    CSRF exempt : légitime car
    - la clé API joue l'auth forte pour cette seule requête
    - le client Cordova/WebView n'a pas encore de cookie CSRF
    - les requêtes suivantes (avec cookie session) auront la protection CSRF normale

    Les bodies 401 sont intentionnellement vides : aucune info leak pour
    distinguer missing/invalid/revoked (side-channel évité). Seul le 400
    (legacy V1) renvoie un message explicite car cet état n'est pas
    sensible pour la sécurité (juste un flag de dette de code).
    / 401 bodies are intentionally empty: no info leak to distinguish
    missing/invalid/revoked (avoids side-channels). Only 400 (legacy V1)
    returns a descriptive message because that state is not security-
    sensitive (just a code-debt flag).

    COMMUNICATION :
    Reçoit : POST form-data avec champ 'api_key'=<key>
    Émet : 302 HttpResponseRedirect + Set-Cookie: sessionid=<key>
           - terminal_role KI (kiosque) → /kiosk/
           - autres rôles (LB, TI, ...) → /laboutik/caisse/
    Erreurs : 401 si clé absente/invalide/révoquée, 400 si clé V1, 429 si throttle
    """

    permission_classes = [AllowAny]
    throttle_classes = [BridgeThrottle]

    def post(self, request):
        # Extraction de la clé depuis le POST form-data
        # / Extract key from POST form-data
        api_key_string = request.POST.get("api_key", "").strip()

        # Pour l'injection conditionnelle de cordova.js afin de récupérer les plugin
        type_app = request.POST.get("type_app", "unknown").strip()

        if not api_key_string:
            # Log : tentative d'accès sans api_key dans le POST
            # / Log: access attempt without api_key in POST body
            logger.warning(
                "laboutik bridge: missing api_key in POST body from %s",
                request.META.get("REMOTE_ADDR"),
            )
            return HttpResponse(status=401)

        # Validation de la clé
        # / Key validation
        from BaseBillet.models import LaBoutikAPIKey

        try:
            api_key = LaBoutikAPIKey.objects.get_from_key(api_key_string)
        except LaBoutikAPIKey.DoesNotExist:
            # Log : clé API inconnue (possibly brute-force)
            # / Log: unknown API key (possibly brute-force)
            logger.warning(
                "laboutik bridge: unknown API key attempt from %s",
                request.META.get("REMOTE_ADDR"),
            )
            return HttpResponse(status=401)

        # Clé V1 sans user lié : non bridgeable
        # / V1 key without linked user: cannot be bridged
        if api_key.user is None:
            logger.info(
                "laboutik bridge: legacy V1 key used (name=%s), bridge refused",
                api_key.name,
            )
            return HttpResponse(
                _(
                    "Legacy API key, bridge flow not available. Please re-pair the device."
                ),
                status=400,
            )

        # User révoqué ?
        # / User revoked?
        term_user = api_key.user
        if not term_user.is_active:
            logger.warning(
                "laboutik bridge: revoked TermUser %s attempted bridge",
                term_user.email,
            )
            return HttpResponse(status=401)

        # Login Django natif : pose le cookie sessionid
        # / Native Django login: sets sessionid cookie
        login(request, term_user)

        # Session courte pour les terminaux (12h)
        # / Short session for terminals (12h)
        request.session.set_expiry(60 * 60 * 12)

        logger.info(
            "laboutik bridge: session opened for terminal %s",
            term_user.email,
        )
        # ajout du paramètres de requête type_app afin d'être récupérer par le front et le back après redirection
        # / append type_app query param so front and back can pick it up after redirect
        #
        # Routage selon le role du terminal : les bornes kiosk (KI) vont vers /kiosk/,
        # tous les autres roles (LB, TI...) gardent la caisse LaBoutik historique.
        # / Route by terminal role: kiosk terminals (KI) go to /kiosk/, all other
        # roles (LB, TI...) keep the historical LaBoutik POS.
        from AuthBillet.models import TibilletUser

        if term_user.terminal_role == TibilletUser.ROLE_KIOSQUE:
            return HttpResponseRedirect("/kiosk/?type_app=" + type_app)
        return HttpResponseRedirect("/laboutik/caisse?type_app=" + type_app)

