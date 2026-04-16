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
from decimal import Decimal
from json import dumps

from django.conf import settings
from django.contrib.auth import login
from django.db import transaction as db_transaction
from django.http import Http404, HttpResponse
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
from django.db import connection
from django.db.models import F, Max, Prefetch, Sum, Count, Q
from django.db.models.functions import Coalesce

from fedow_core.exceptions import SoldeInsuffisant
from fedow_core.models import Asset, Transaction
from fedow_core.services import AssetService, TransactionService, WalletService

from AuthBillet.models import Wallet
from AuthBillet.utils import get_or_create_user
from django.utils import timezone as dj_timezone

from BaseBillet.models import (
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
from BaseBillet.permissions import HasLaBoutikAccess, HasLaBoutikTerminalAccess
from QrcodeCashless.models import CarteCashless
from laboutik.models import (
    LaboutikConfiguration,
    PointDeVente,
    CartePrimaire,
    Table,
    CommandeSauvegarde,
    ArticleCommandeSauvegarde,
    ClotureCaisse,
    CorrectionPaiement,
    SortieCaisse,
    HistoriqueFondDeCaisse,
)
from laboutik.serializers import (
    ClientIdentificationSerializer,
    CartePrimaireSerializer,
    PanierSerializer,
    CommandeSerializer,
    ArticleCommandeSerializer,
    ClotureSerializer,
    EnvoyerRapportSerializer,
)
from laboutik.reports import RapportComptableService
from laboutik.utils import method as payment_method
from inventaire.models import Stock, TypeMouvement
from inventaire.serializers import MouvementRapideSerializer
from inventaire.services import StockService
from wsocket.broadcast import broadcast_stock_update
from laboutik.integrity import (
    calculer_hmac,
    obtenir_previous_hmac,
    calculer_total_ht,
    ligne_couverte_par_cloture,
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

# Traduction des codes DB (PaymentMethod.choices) pour l'affichage POS
# / DB code (PaymentMethod.choices) translations for POS display
LABELS_MOYENS_PAIEMENT_DB = {
    PaymentMethod.CASH: _("Espèces"),
    PaymentMethod.CC: _("Carte bancaire"),
    PaymentMethod.CHEQUE: _("Chèque"),
    PaymentMethod.LOCAL_EURO: _("Cashless"),
    PaymentMethod.LOCAL_GIFT: _("Cadeau"),
    PaymentMethod.FREE: _("Offert"),
}

# UUID de l'article "consigne" — déclenche un flux de remboursement spécial
# UUID of the "deposit" article — triggers a special refund flow
UUID_ARTICLE_CONSIGNE = "8f08b90d-d3f0-49da-9dbd-8be795f689ef"

# Catégorie par défaut quand un produit n'a pas de categorie_pos
# Default category when a product has no categorie_pos
CATEGORIE_PAR_DEFAUT = {
    "id": "default",
    "name": "Divers",
    "icon": "fa-angry",
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


def _construire_state(point_de_vente=None, carte_primaire_obj=None):
    """
    Construit le dictionnaire "state" à chaque requête.
    Builds the "state" dictionary on each request.

    Le state est lu côté client (JS) via stateJson pour piloter l'interface.
    State is read client-side (JS) via stateJson to drive the interface.
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
                    reservation__datetime__gt=now - timedelta(minutes=15),
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


def _construire_donnees_articles(point_de_vente_instance, events_billetterie=None):
    """
    Construit la liste de dicts articles au format attendu par les templates.
    Builds the list of article dicts in the format expected by templates.

    LOCALISATION : laboutik/views.py

    Chaque produit doit avoir au moins un prix publié en euros (asset=null).
    Les produits sans prix sont ignorés.
    Each product must have at least one published EUR price (asset=null).
    Products without a price are skipped.

    """
    # Prefetch filtré : seuls les prix publiés en euros, triés par ordre d'affichage.
    # Le .filter() dans la boucle utiliserait une nouvelle requête par produit (N+1).
    # Avec Prefetch(queryset=...), Django charge tout en 1 requête et filtre en mémoire.
    # Filtered prefetch: only published EUR prices, sorted by display order.
    prix_euros_prefetch = Prefetch(
        "prices",
        queryset=Price.objects.filter(publish=True, asset__isnull=True).order_by(
            "order"
        ),
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
        # Produits de recharge sans Asset lie, ou Asset archive/inactif → ne pas afficher
        # / Top-up products without linked Asset, or archived/inactive Asset → skip
        if product.methode_caisse in METHODES_RECHARGE:
            if (
                product.asset is None
                or product.asset.archive
                or not product.asset.active
            ):
                continue

        # Premier prix publié en euros (déjà filtré par le Prefetch)
        # First published EUR price (already filtered by Prefetch)
        if not product.prix_euros:
            continue
        prix_obj = product.prix_euros[0]

        prix_en_centimes = int(round(prix_obj.prix * 100))

        # Catégorie POS du produit (ou catégorie par défaut)
        # Product POS category (or default category)
        categorie_pos = product.categorie_pos
        if categorie_pos is not None:
            icone_cat_brute = categorie_pos.icon or ""
            if icone_cat_brute.startswith("fa"):
                icone_type_cat = "fa"
            elif icone_cat_brute:
                icone_type_cat = "ms"
            else:
                icone_type_cat = ""
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
                tarifs.append(
                    {
                        "price_uuid": str(p.uuid),
                        "name": p.name,
                        "prix_centimes": int(round(p.prix * 100)),
                        "free_price": p.free_price,
                        "poids_mesure": p.poids_mesure,
                        "unite_saisie_label": "",  # sera enrichi ci-dessous / will be enriched below
                        "prix_reference_label": "",  # sera enrichi ci-dessous / will be enriched below
                        "subscription_label": p.get_subscription_type_display()
                        if hasattr(p, "get_subscription_type_display")
                        else "",
                    }
                )

        # --- Enrichissement poids/mesure : unités de saisie et labels de prix de référence ---
        # Déterminé à partir du Stock lié (unite GR → grammes/kg, CL → centilitres/litres).
        # / Weight-based enrichment: input units and reference price labels.
        # Determined from linked Stock (unite GR → grams/kg, CL → centilitres/litres).
        unite_saisie_label = "g"
        prix_reference_label = "/kg"
        if a_poids_mesure:
            try:
                stock_du_produit_pm = product.stock_inventaire
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
            # Enrichir les tarifs poids_mesure avec l'unité de saisie
            # / Enrich weight-based prices with input unit
            for t in tarifs:
                if t.get("poids_mesure"):
                    t["unite_saisie_label"] = unite_saisie_label
                    t["prix_reference_label"] = prix_reference_label

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

        # Détection du système d'icône selon le nom stocké :
        #   - FontAwesome : noms préfixés par "fa" (ex: "fa-coffee", "fas-X")
        #   - Material Symbols : noms avec underscores, sans préfixe "fa" (ex: "local_bar")
        # Icon system detection based on stored name:
        #   - FontAwesome : names prefixed with "fa" (e.g. "fa-coffee", "fas-X")
        #   - Material Symbols : underscore names, no "fa" prefix (e.g. "local_bar")
        if icone_brute.startswith("fa"):
            icone_article = icone_brute
            icone_type = "fa"
        elif icone_brute:
            icone_article = icone_brute
            icone_type = "ms"
        else:
            icone_article = ""
            icone_type = ""

        article_dict = {
            "id": str(product.uuid),
            "name": product.name,
            "prix": prix_en_centimes,
            "categorie": categorie_dict,
            "couleur_backgr": couleur_backgr,
            "couleur_texte": couleur_texte_article,
            "icone": icone_article,
            "icone_type": icone_type,  # "fa" | "ms" | ""
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
                icone_brute = (
                    product.icon_pos
                    or (categorie_pos.icon if categorie_pos else None)
                    or "fa-ticket-alt"
                )
                if icone_brute.startswith("fa"):
                    icone_type = "fa"
                elif icone_brute:
                    icone_type = "ms"
                else:
                    icone_type = "fa"
                    icone_brute = "fa-ticket-alt"

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
                            "icon": "fa-calendar-alt",
                            "icone_type": "fa",
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
        icone_cat = categorie.icon or ""
        # Détection du système d'icône (même logique que pour les articles)
        # Icon system detection (same logic as for articles)
        if icone_cat.startswith("fa"):
            icone_type_cat = "fa"
        elif icone_cat:
            icone_type_cat = "ms"
        else:
            icone_type_cat = "fa"
            icone_cat = "fa-th"
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
                    "icon": "fa-calendar-alt",
                    "icone_type": "fa",
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

    # 3. Pas de wallet → créer un wallet éphémère
    # 3. No wallet → create an ephemeral wallet
    wallet = Wallet.objects.create(
        origin=connection.tenant,
        name=f"Éphémère - {carte.tag_id}",
    )
    carte.wallet_ephemere = wallet
    carte.save(update_fields=["wallet_ephemere"])
    logger.info(f"Wallet éphémère créé pour carte {carte.tag_id}: {wallet.uuid}")
    return wallet


def _render_erreur_toast(request, msg):
    """
    Rend un partial d'erreur compatible avec le pattern POS (toast dans #messages).
    / Renders an error partial compatible with POS toast pattern (in #messages).
    """
    contexte = {
        "msg_type": "warning",
        "msg_content": str(msg),
        "selector_bt_retour": "#messages",
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
    Product.RECHARGE_TEMPS,
)

# Recharges payantes : le client doit payer (especes, CB, cheque)
# Paid top-ups: the client must pay (cash, card, check)
METHODES_RECHARGE_PAYANTES = (Product.RECHARGE_EUROS,)

# Recharges gratuites : credit automatique, pas de paiement demande
# Free top-ups: auto-credit, no payment asked
METHODES_RECHARGE_GRATUITES = (Product.RECHARGE_CADEAU, Product.RECHARGE_TEMPS)


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
        state = _construire_state()
        context = {
            "state": state,
            "stateJson": dumps(state),
            "method": request.method,
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
        - 0 PV → "Aucun point de vente configuré" / no POS configured
        - 1 PV → redirect direct vers le PV / direct redirect to POS
        - N PV → choix du PV (hx_choose_pv.html) / POS selection
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
        url_avec_params = (
            f"{url_point_de_vente}?uuid_pv={pv.uuid}&tag_id_cm={tag_id_carte_manager}"
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
        state = _construire_state(pv, carte_primaire_obj)

        # --- Choisir le template selon le mode du point de vente ---
        # --- Choose the template based on the point of sale mode ---

        # Par défaut : mode restaurant → afficher le choix des tables
        # Default: restaurant mode → show table selection
        titre_page = _("Choisir une table")
        template_name = "laboutik/views/tables.html"

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
        Cloture journaliere (niveau J) : calcule le rapport via RapportComptableService,
        cree ClotureCaisse avec numero sequentiel et total perpetuel, ferme les tables.
        / Daily closure (level J): computes report via RapportComptableService,
        creates ClotureCaisse with sequential number and perpetual total, closes tables.

        LOCALISATION : laboutik/views.py
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

        # --- 4. Calculer datetime_ouverture automatiquement ---
        # Trouver la derniere cloture journaliere de ce PV
        # / Find the last daily closure for this PV
        derniere_cloture = (
            ClotureCaisse.objects.filter(
                point_de_vente=point_de_vente,
                niveau=ClotureCaisse.JOURNALIERE,
            )
            .order_by("-datetime_cloture")
            .first()
        )

        if derniere_cloture:
            # datetime_ouverture = 1ere LigneArticle VALID apres la derniere cloture
            # / datetime_ouverture = 1st VALID LigneArticle after the last closure
            premiere_vente = (
                LigneArticle.objects.filter(
                    sale_origin=SaleOrigin.LABOUTIK,
                    status=LigneArticle.VALID,
                    datetime__gt=derniere_cloture.datetime_cloture,
                )
                .order_by("datetime")
                .first()
            )
        else:
            # Aucune cloture precedente : 1ere LigneArticle VALID tous temps confondus
            # / No previous closure: 1st VALID LigneArticle ever
            premiere_vente = (
                LigneArticle.objects.filter(
                    sale_origin=SaleOrigin.LABOUTIK,
                    status=LigneArticle.VALID,
                )
                .order_by("datetime")
                .first()
            )

        if not premiere_vente:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Aucune vente à clôturer"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        datetime_ouverture = premiere_vente.datetime

        # --- 5. Calculer le rapport via RapportComptableService ---
        # --- 5. Compute the report via RapportComptableService ---
        datetime_cloture = dj_timezone.now()
        service = RapportComptableService(
            point_de_vente, datetime_ouverture, datetime_cloture
        )
        rapport = service.generer_rapport_complet()
        totaux = rapport["totaux_par_moyen"]
        hash_lignes = service.calculer_hash_lignes()

        # Extraire les totaux pour la ClotureCaisse et l'affichage
        # / Extract totals for ClotureCaisse and display
        total_especes = totaux["especes"]
        total_carte_bancaire = totaux["carte_bancaire"]
        total_cashless = totaux["cashless"]
        total_general = totaux["total"]
        nombre_transactions = service.lignes.count()

        # --- 6. Bloc atomique : numero sequentiel + total perpetuel + creation ---
        # La cloture est GLOBALE au tenant (couvre tous les PV).
        # Le numero sequentiel est par niveau, pas par PV.
        # Le point_de_vente est informatif (d'ou la cloture a ete declenchee).
        # / Closure is GLOBAL to the tenant (covers all POS).
        # Sequential number is per level, not per POS.
        # point_de_vente is informational (where closure was triggered from).
        with db_transaction.atomic():
            # Numero sequentiel global par niveau : dernier +1, avec verrou
            # / Global sequential number per level: last +1, with lock
            clotures_niveau = (
                ClotureCaisse.objects.select_for_update()
                .filter(
                    niveau=ClotureCaisse.JOURNALIERE,
                )
                .order_by("-numero_sequentiel")
            )

            dernier_seq = clotures_niveau.first()
            numero_sequentiel = (
                (dernier_seq.numero_sequentiel + 1) if dernier_seq else 1
            )

            # Total perpetuel : mise a jour atomique avec F() puis refresh.
            # On utilise update_or_create pour garantir que la ligne existe
            # meme si django-solo a cache un objet non persiste
            # (piege 9.86 : get_solo peut retourner pk=1 sans ligne en DB).
            # Attention : variable `_created` (pas `_`) — `_` est reserve a gettext
            # plus loin dans cette fonction (piege 9.36).
            # / Perpetual total: atomic update with F() then refresh.
            # update_or_create guarantees the row exists even if django-solo
            # cached a non-persisted object (trap 9.86).
            # Use `_created` (not `_`) — `_` shadows gettext below (trap 9.36).
            config, _created = LaboutikConfiguration.objects.update_or_create(pk=1)
            LaboutikConfiguration.objects.filter(pk=config.pk).update(
                total_perpetuel=F("total_perpetuel") + total_general
            )
            config.refresh_from_db()

            # Creer la ClotureCaisse — point_de_vente = informatif
            # / Create ClotureCaisse — point_de_vente = informational
            cloture = ClotureCaisse.objects.create(
                point_de_vente=point_de_vente,
                responsable=request.user if request.user.is_authenticated else None,
                datetime_ouverture=datetime_ouverture,
                datetime_cloture=datetime_cloture,
                total_especes=total_especes,
                total_carte_bancaire=total_carte_bancaire,
                total_cashless=total_cashless,
                total_general=total_general,
                nombre_transactions=nombre_transactions,
                rapport_json=rapport,
                niveau=ClotureCaisse.JOURNALIERE,
                numero_sequentiel=numero_sequentiel,
                total_perpetuel=config.total_perpetuel,
                hash_lignes=hash_lignes,
            )

        # --- 7. Fermer les tables ouvertes (OCCUPEE ou SERVIE → LIBRE) ---
        # --- 7. Close open tables (OCCUPIED or SERVED → FREE) ---
        Table.objects.filter(
            statut__in=[Table.OCCUPEE, Table.SERVIE],
        ).update(statut=Table.LIBRE)

        # --- Annuler les commandes encore ouvertes ---
        # --- Cancel still-open orders ---
        CommandeSauvegarde.objects.filter(
            statut=CommandeSauvegarde.OPEN,
        ).update(statut=CommandeSauvegarde.CANCEL)

        # --- 8. Imprimer le Ticket Z sur l'imprimante du PV ---
        # / Print the Z-ticket on the POS printer
        if point_de_vente.printer and point_de_vente.printer.active:
            from laboutik.printing.formatters import formatter_ticket_cloture
            from laboutik.printing.tasks import imprimer_async

            ticket_z_data = formatter_ticket_cloture(cloture)
            schema_name = connection.schema_name
            imprimer_async.delay(
                str(point_de_vente.printer.pk),
                ticket_z_data,
                schema_name,
            )

        # --- 9. Logger avec les infos enrichies ---
        # --- 9. Log with enriched info ---
        logger.info(
            f"Cloture caisse: PV={point_de_vente.name}, "
            f"niveau={cloture.niveau}, seq={numero_sequentiel}, "
            f"total={total_general}cts, perpetuel={config.total_perpetuel}cts, "
            f"transactions={nombre_transactions}"
        )

        # --- 9. Convertir la TVA en euros pour l'affichage ---
        # --- 9. Convert VAT to euros for display ---
        rapport_tva_euros = {}
        for taux_label, tva_data in rapport["tva"].items():
            rapport_tva_euros[taux_label] = {
                "total_ht_euros": f"{tva_data['total_ht'] / 100:.2f}",
                "total_tva_euros": f"{tva_data['total_tva'] / 100:.2f}",
                "total_ttc_euros": f"{tva_data['total_ttc'] / 100:.2f}",
            }

        # --- 10. Retourner le rapport ---
        # --- 10. Return the report ---
        context = {
            "cloture": cloture,
            "rapport": rapport,
            "rapport_tva_euros": rapport_tva_euros,
            "total_especes_euros": total_especes / 100,
            "total_cb_euros": total_carte_bancaire / 100,
            "total_nfc_euros": total_cashless / 100,
            "total_general_euros": total_general / 100,
            "nombre_transactions": nombre_transactions,
            "currency_data": CURRENCY_DATA,
        }
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
        Telecharge le rapport de cloture en PDF.
        Downloads the closure report as PDF.

        LOCALISATION : laboutik/views.py
        """
        from laboutik.pdf import generer_pdf_cloture

        try:
            cloture = ClotureCaisse.objects.select_related(
                "point_de_vente",
                "responsable",
            ).get(uuid=pk)
        except ClotureCaisse.DoesNotExist:
            raise Http404

        pdf_bytes = generer_pdf_cloture(cloture)

        date_str = cloture.datetime_cloture.strftime("%Y%m%d_%H%M")
        nom_fichier = f"cloture_{date_str}.pdf"

        from django.http import HttpResponse

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
        return response

    @action(
        detail=True, methods=["get"], url_path="rapport_csv", url_name="rapport_csv"
    )
    def rapport_csv(self, request, pk=None):
        """
        GET /laboutik/caisse/<uuid>/rapport_csv/
        Telecharge le rapport de cloture en CSV.
        Downloads the closure report as CSV.

        LOCALISATION : laboutik/views.py
        """
        from laboutik.csv_export import generer_csv_cloture

        try:
            cloture = ClotureCaisse.objects.select_related(
                "point_de_vente",
                "responsable",
            ).get(uuid=pk)
        except ClotureCaisse.DoesNotExist:
            raise Http404

        csv_string = generer_csv_cloture(cloture)

        date_str = cloture.datetime_cloture.strftime("%Y%m%d_%H%M")
        nom_fichier = f"cloture_{date_str}.csv"

        from django.http import HttpResponse

        response = HttpResponse(csv_string, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{nom_fichier}"'
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
        Envoie le rapport de cloture par email (PDF + CSV en PJ) via Celery.
        Sends the closure report by email (PDF + CSV attachments) via Celery.

        LOCALISATION : laboutik/views.py
        """
        from laboutik.tasks import envoyer_rapport_cloture

        try:
            cloture = ClotureCaisse.objects.get(uuid=pk)
        except ClotureCaisse.DoesNotExist:
            raise Http404

        serializer = EnvoyerRapportSerializer(data=request.data)
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

        email = serializer.validated_data.get("email") or None

        envoyer_rapport_cloture.delay(
            connection.schema_name,
            str(cloture.uuid),
            email,
        )

        context = {
            "msg_type": "info",
            "msg_content": _("Rapport envoyé par email"),
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

        # Recuperer le PV et son imprimante / Get POS and its printer
        try:
            point_de_vente = PointDeVente.objects.select_related("printer").get(
                uuid=uuid_pv
            )
        except (PointDeVente.DoesNotExist, ValueError):
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Point de vente introuvable"),
                },
                status=404,
            )

        if not point_de_vente.printer or not point_de_vente.printer.active:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _(
                        "Aucune imprimante configuree pour ce point de vente"
                    ),
                },
                status=400,
            )

        # Calculer le rapport du service en cours / Compute current shift report
        datetime_ouverture = _calculer_datetime_ouverture_service()
        if datetime_ouverture is None:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Aucune vente en cours — rien a imprimer"),
                },
                status=400,
            )

        datetime_fin = dj_timezone.now()
        service = RapportComptableService(None, datetime_ouverture, datetime_fin)
        totaux_par_moyen = service.calculer_totaux_par_moyen()
        solde_caisse = service.calculer_solde_caisse()
        nb_transactions = service.lignes.count()

        # Formater et imprimer / Format and print
        from laboutik.printing.formatters import formatter_ticket_x
        from laboutik.printing.tasks import imprimer_async

        ticket_data = formatter_ticket_x(
            totaux_par_moyen, solde_caisse, datetime_ouverture, nb_transactions
        )

        schema_name = connection.schema_name
        imprimer_async.delay(
            str(point_de_vente.printer.pk),
            ticket_data,
            schema_name,
        )

        return render(
            request,
            "laboutik/partial/hx_messages.html",
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
        Affiche le formulaire avec dates debut/fin optionnelles.
        / Shows the form with optional start/end dates.

        POST /laboutik/caisse/export-fiscal/
        Genere et telecharge l'archive ZIP signee HMAC.
        / Generates and downloads the HMAC-signed ZIP archive.

        LOCALISATION : laboutik/views.py

        FLUX :
        1. GET : affiche le formulaire (template hx_export_fiscal.html)
        2. POST : valide les dates, genere les fichiers, calcule les hash,
           empaquete en ZIP, journalise l'operation, renvoie le ZIP.
        / 1. GET: shows the form
        2. POST: validates dates, generates files, computes hashes,
           packages into ZIP, logs the operation, returns the ZIP.
        """
        from datetime import date as date_type

        from django.db import connection
        from django.http import HttpResponse

        from laboutik.archivage import (
            calculer_hash_fichiers,
            creer_entree_journal,
            empaqueter_zip,
            generer_fichiers_archive,
        )

        config = LaboutikConfiguration.get_solo()

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

        # --- POST : generation de l'archive ZIP ---
        # --- POST: ZIP archive generation ---

        # Recuperer la cle HMAC / Get the HMAC key
        cle = config.get_or_create_hmac_key()
        if not cle:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Cle HMAC non configuree. Export impossible."),
                },
                status=500,
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

        schema = connection.schema_name

        # Generer les fichiers, calculer les hash, empaqueter en ZIP
        # / Generate files, compute hashes, package into ZIP
        fichiers = generer_fichiers_archive(schema, debut, fin)
        hash_json = calculer_hash_fichiers(fichiers, cle)
        zip_bytes = empaqueter_zip(fichiers, hash_json)

        # Journaliser l'export / Log the export
        details = {
            "schema": schema,
            "debut": debut_str or None,
            "fin": fin_str or None,
            "nb_fichiers": len(fichiers),
            "taille_zip": len(zip_bytes),
        }
        creer_entree_journal(
            type_operation="EXPORT_FISCAL",
            details=details,
            cle_secrete=cle,
            operateur=request.user if request.user.is_authenticated else None,
        )

        # Reponse ZIP en telechargement / ZIP download response
        date_label = dj_timezone.localtime(dj_timezone.now()).strftime("%Y%m%d_%H%M")
        filename = f"export_fiscal_{schema}_{date_label}.zip"
        response = HttpResponse(zip_bytes, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

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
    #  Charger plan comptable — jeu de comptes par defaut                      #
    #  Load chart of accounts — default account set                            #
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
        Charge un jeu de comptes comptables par defaut (bar_resto ou association).
        / Loads a default chart of accounts set (bar_resto or association).

        LOCALISATION : laboutik/views.py
        """
        from django.core.management import call_command
        from django.db import connection

        jeu = request.POST.get("jeu", "").strip()
        if jeu not in ("bar_resto", "association"):
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Jeu de comptes invalide."),
                },
                status=400,
            )

        # Verifier si des comptes existent deja — si oui, forcer le reset
        # Sinon la commande afficherait un warning et ne ferait rien
        # / Check if accounts already exist — if so, force reset
        from laboutik.models import CompteComptable

        nb_existants = CompteComptable.objects.count()

        try:
            call_command(
                "charger_plan_comptable",
                schema=connection.schema_name,
                jeu=jeu,
                reset=nb_existants > 0,
            )
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

        message = _("Plan comptable charge avec succes.")
        if nb_existants > 0:
            message = _(
                "Plan comptable remplace avec succes (%(nb)s comptes precedents supprimes)."
            ) % {
                "nb": nb_existants,
            }

        return render(
            request,
            "laboutik/partial/hx_messages.html",
            {
                "msg_type": "success",
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
        params_ventes = f"uuid_pv={uuid_pv}&tag_id_cm={tag_id_cm}" if uuid_pv else ""

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
        params_ventes = f"uuid_pv={uuid_pv}&tag_id_cm={tag_id_cm}" if uuid_pv else ""

        # Calculer le solde caisse via le meme service que le Ticket X
        # Evite la duplication de logique (fond + especes - sorties).
        # / Calculate cash balance via the same service as Ticket X
        # Avoids logic duplication (float + cash - withdrawals).
        datetime_ouverture = _calculer_datetime_ouverture_service()
        if datetime_ouverture:
            datetime_fin = dj_timezone.now()
            service = RapportComptableService(None, datetime_ouverture, datetime_fin)
            solde_caisse = service.calculer_solde_caisse()
            fond_de_caisse_centimes = solde_caisse["fond_de_caisse"]
            entrees_especes_centimes = solde_caisse["entrees_especes"]
            solde_total_centimes = solde_caisse["solde"]
        else:
            config = LaboutikConfiguration.get_solo()
            fond_de_caisse_centimes = config.fond_de_caisse or 0
            entrees_especes_centimes = 0
            solde_total_centimes = fond_de_caisse_centimes

        context = {
            "uuid_pv": uuid_pv,
            "coupures": _COUPURES_POUR_TEMPLATE,
            "coupures_paires": _COUPURES_PAIRES_POUR_TEMPLATE,
            "params_ventes": params_ventes,
            # Données pour la validation JS (indicatives — le serveur re-vérifie)
            # / Data for JS validation (indicative — server re-validates)
            "fond_de_caisse_centimes": fond_de_caisse_centimes,
            "entrees_especes_centimes": entrees_especes_centimes,
            # Chaînes pré-formatées pour l'affichage dans le template
            # / Pre-formatted strings for display in the template
            "fond_de_caisse_euros": f"{fond_de_caisse_centimes / 100:.2f}".replace(
                ".", ","
            ),
            "entrees_especes_euros": f"{entrees_especes_centimes / 100:.2f}".replace(
                ".", ","
            ),
            "solde_total_euros": f"{solde_total_centimes / 100:.2f}".replace(".", ","),
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
        # Validation du PV et de la note via serializer DRF
        # / Validate POS and note via DRF serializer
        from laboutik.serializers import SortieDeCaisseSerializer

        serializer = SortieDeCaisseSerializer(data=request.POST)
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

        uuid_pv = serializer.validated_data["uuid_pv"]
        note = serializer.validated_data.get("note", "").strip()

        # Recuperer le point de vente
        # / Get the point of sale
        try:
            point_de_vente = PointDeVente.objects.get(uuid=uuid_pv)
        except PointDeVente.DoesNotExist:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Point de vente introuvable"),
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
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Aucune coupure saisie"),
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

        # Propager les params pour le bouton retour
        # / Propagate params for the back button
        tag_id_cm = request.POST.get("tag_id_cm", "")
        params_ventes = f"uuid_pv={uuid_pv}&tag_id_cm={tag_id_cm}" if uuid_pv else ""

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
    #  Menu Ventes — Ticket X + liste des ventes (Session 16)                  #
    #  Sales menu — Ticket X + sales list (Session 16)                         #
    # ----------------------------------------------------------------------- #

    @action(
        detail=False,
        methods=["get"],
        url_path="recap-en-cours",
        url_name="recap_en_cours",
    )
    def recap_en_cours(self, request):
        """
        GET /laboutik/caisse/recap-en-cours/?vue=toutes|par_pv|par_moyen
        Ticket X : synthese comptable du service en cours (lecture seule).
        Pas de creation de ClotureCaisse. Appelle RapportComptableService.
        / Ticket X: accounting summary of the current shift (read-only).
        No ClotureCaisse created. Calls RapportComptableService.

        LOCALISATION : laboutik/views.py

        FLUX :
        1. Calcule datetime_ouverture (1ere vente apres derniere cloture journaliere)
        2. Instancie RapportComptableService(pv=None, debut, fin=now())
        3. Selon le param ?vue : genere le rapport correspondant
        4. Rend hx_recap_en_cours.html dans #products-container
        """
        datetime_ouverture = _calculer_datetime_ouverture_service()
        vue = request.GET.get("vue", "toutes")

        # Si aucune vente depuis la derniere cloture, afficher un message
        # / If no sales since last closure, show a message
        if datetime_ouverture is None:
            context = {
                "aucune_vente": True,
                "vue": vue,
            }
            return _rendre_vue_ventes(
                request, "laboutik/partial/hx_recap_en_cours.html", context
            )

        datetime_fin = dj_timezone.now()
        service = RapportComptableService(None, datetime_ouverture, datetime_fin)

        # Construire le contexte selon la vue demandee
        # / Build context based on the requested view
        context = {
            "vue": vue,
            "aucune_vente": False,
            "datetime_ouverture": datetime_ouverture,
            "datetime_fin": datetime_fin,
            "nb_transactions": service.lignes.count(),
        }

        if vue == "par_pv":
            context["ventilation_par_pv"] = service.calculer_ventilation_par_pv()
            context["totaux_par_moyen"] = service.calculer_totaux_par_moyen()
        elif vue == "par_moyen":
            context["synthese_operations"] = service.calculer_synthese_operations()
            context["totaux_par_moyen"] = service.calculer_totaux_par_moyen()
        elif vue == "detail_articles":
            context["detail_ventes"] = service.calculer_detail_ventes()
        else:
            # Vue "toutes" : totaux, TVA, solde
            # / "toutes" view: totals, VAT, cash balance
            context["totaux_par_moyen"] = service.calculer_totaux_par_moyen()
            context["tva"] = service.calculer_tva()
            context["solde_caisse"] = service.calculer_solde_caisse()

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
        3. Appelle generer_rapport_complet() (13 sections)
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
        GET /laboutik/caisse/liste-ventes/?pv=uuid&moyen=CA&page=1
        Liste paginee des ventes du service en cours.
        Pagination HTMX avec scroll infini (hx-trigger="revealed").
        / Paginated list of sales for the current shift.
        HTMX pagination with infinite scroll.

        LOCALISATION : laboutik/views.py
        """
        datetime_ouverture = _calculer_datetime_ouverture_service()

        if datetime_ouverture is None:
            context = {
                "aucune_vente": True,
                "ventes_groupees": [],
                "page_courante": 1,
                "a_page_suivante": False,
            }
            return _rendre_vue_ventes(
                request, "laboutik/partial/hx_liste_ventes.html", context
            )

        # Queryset de base : lignes valides du service en cours
        # / Base queryset: valid lines from current shift
        lignes = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            datetime__gte=datetime_ouverture,
            datetime__lte=dj_timezone.now(),
            status=LigneArticle.VALID,
        )

        # Appliquer les filtres GET
        # / Apply GET filters
        filtre_pv = request.GET.get("pv")
        filtre_moyen = request.GET.get("moyen")

        if filtre_pv:
            lignes = lignes.filter(point_de_vente__uuid=filtre_pv)
        if filtre_moyen:
            lignes = lignes.filter(payment_method=filtre_moyen)

        # Regrouper par uuid_transaction cote PostgreSQL (GROUP BY).
        # Les lignes sans uuid_transaction utilisent leur uuid comme cle.
        # Coalesce(uuid_transaction, uuid) = COALESCE(uuid_transaction, uuid) en SQL.
        # Tout le travail est fait par la DB : pas de chargement en memoire Python.
        # / Group by uuid_transaction on the PostgreSQL side (GROUP BY).
        # Lines without uuid_transaction use their uuid as key.
        # All work done by the DB: no Python in-memory loading.
        ventes_requete = (
            lignes.values(
                cle_vente=Coalesce("uuid_transaction", "uuid"),
            )
            .annotate(
                derniere_datetime=Max("datetime"),
                total=Sum("amount"),
                nb_articles=Count("uuid"),
                moyen_paiement=Max("payment_method"),
                nom_pv=Max("point_de_vente__name"),
            )
            .order_by("-derniere_datetime")
        )

        # Pagination SQL native via slicing Django (traduit en LIMIT/OFFSET)
        # / Native SQL pagination via Django slicing (translates to LIMIT/OFFSET)
        try:
            page = int(request.GET.get("page", 1))
        except (ValueError, TypeError):
            page = 1
        if page < 1:
            page = 1
        taille_page = 20
        offset = (page - 1) * taille_page
        ventes_page = list(ventes_requete[offset : offset + taille_page])
        a_page_suivante = ventes_requete[
            offset + taille_page : offset + taille_page + 1
        ].exists()

        # Ajouter le label humain du moyen de paiement a chaque vente
        # (le queryset renvoie le code brut "CA", "CC", etc.)
        # / Add human-readable payment method label to each sale
        for vente in ventes_page:
            code_moyen = vente.get("moyen_paiement", "")
            vente["moyen_paiement_label"] = LABELS_MOYENS_PAIEMENT_DB.get(
                code_moyen, code_moyen
            )

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
            "ventes_groupees": ventes_page,
            "page_courante": page,
            "a_page_suivante": a_page_suivante,
            "page_suivante": page + 1,
            "filtre_pv": filtre_pv or "",
            "filtre_moyen": filtre_moyen or "",
            "points_de_vente": list(points_de_vente),
            "moyens_paiement": [
                {"code": PaymentMethod.CASH, "label": _("Espèces")},
                {"code": PaymentMethod.CC, "label": _("Carte bancaire")},
                {"code": PaymentMethod.LOCAL_EURO, "label": _("Cashless")},
                {"code": PaymentMethod.LOCAL_GIFT, "label": _("Cadeau")},
                {"code": PaymentMethod.CHEQUE, "label": _("Chèque")},
            ],
        }
        return _rendre_vue_ventes(
            request, "laboutik/partial/hx_liste_ventes.html", context
        )

    @action(
        detail=False,
        methods=["get"],
        url_path=r"detail-vente/(?P<uuid_transaction>[^/.]+)",
        url_name="detail_vente",
    )
    def detail_vente(self, request, uuid_transaction=None):
        """
        GET /laboutik/caisse/detail-vente/<uuid_transaction>/
        Detail d'une vente : toutes les LigneArticle du meme uuid_transaction.
        / Sale detail: all LigneArticle with the same uuid_transaction.

        LOCALISATION : laboutik/views.py
        """
        # Valider le format UUID avant la requete
        # / Validate UUID format before the query
        try:
            uuid_tx_valide = uuid_module.UUID(str(uuid_transaction))
        except (ValueError, AttributeError):
            context = {
                "msg_type": "warning",
                "msg_content": _("Transaction introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context, status=404
            )

        # Recuperer les lignes de cette transaction.
        # La cle peut etre un uuid_transaction (regroupement) ou un uuid de ligne
        # (ventes sans uuid_transaction, anciennes donnees).
        # On cherche d'abord par uuid_transaction, puis par uuid (pk).
        # / Get all lines for this transaction.
        # The key can be a uuid_transaction (grouped) or a line uuid
        # (sales without uuid_transaction, old data).
        # Try uuid_transaction first, then uuid (pk).
        lignes = (
            LigneArticle.objects.filter(
                uuid_transaction=uuid_tx_valide,
                sale_origin=SaleOrigin.LABOUTIK,
            )
            .select_related(
                "pricesold__productsold__product",
                "pricesold__price",
                "point_de_vente",
            )
            .order_by("datetime")
        )

        # Si pas trouve par uuid_transaction, chercher par uuid (pk de la ligne)
        # / If not found by uuid_transaction, search by uuid (line pk)
        if not lignes.exists():
            lignes = (
                LigneArticle.objects.filter(
                    uuid=uuid_tx_valide,
                    sale_origin=SaleOrigin.LABOUTIK,
                )
                .select_related(
                    "pricesold__productsold__product",
                    "pricesold__price",
                    "point_de_vente",
                )
                .order_by("datetime")
            )

        if not lignes.exists():
            context = {
                "msg_type": "warning",
                "msg_content": _("Transaction introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context, status=404
            )

        # Construire le detail des articles
        # / Build article details
        premiere_ligne = lignes.first()
        articles_detail = []
        total_transaction = 0

        for ligne in lignes:
            nom_article = ""
            nom_tarif = ""
            if ligne.pricesold:
                if ligne.pricesold.productsold:
                    nom_article = ligne.pricesold.productsold.product.name
                if ligne.pricesold.price:
                    nom_tarif = ligne.pricesold.price.name

            articles_detail.append(
                {
                    "nom": nom_article,
                    "tarif": nom_tarif,
                    "qty": ligne.qty,
                    "montant": ligne.amount or 0,
                }
            )
            total_transaction += ligne.amount or 0

        # La correction est possible si le moyen n'est pas NFC
        # et si la ligne n'est pas couverte par une cloture
        # / Correction is possible if method is not NFC
        # and line is not covered by a closure
        moyen_de_la_ligne = premiere_ligne.payment_method or ""
        moyens_nfc = (PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT)
        correction_est_possible = (
            moyen_de_la_ligne not in moyens_nfc
            and not ligne_couverte_par_cloture(premiere_ligne)
        )

        # Label humain du moyen de paiement (ex: "Espèces" au lieu de "CA")
        # / Human-readable payment method label (e.g. "Cash" instead of "CA")
        moyen_paiement_label = LABELS_MOYENS_PAIEMENT_DB.get(
            moyen_de_la_ligne, moyen_de_la_ligne
        )

        context = {
            "uuid_transaction": uuid_transaction,
            "datetime": premiere_ligne.datetime,
            "moyen_paiement": moyen_de_la_ligne,
            "moyen_paiement_label": moyen_paiement_label,
            "nom_pv": premiere_ligne.point_de_vente.name
            if premiere_ligne.point_de_vente
            else "",
            "articles": articles_detail,
            "total": total_transaction,
            "nb_articles": len(articles_detail),
            "correction_possible": correction_est_possible,
            "premiere_ligne_uuid": str(premiere_ligne.uuid),
        }
        return _rendre_vue_ventes(
            request, "laboutik/partial/hx_detail_vente.html", context
        )


# --------------------------------------------------------------------------- #
#  Fonctions utilitaires — Menu Ventes (Session 16)                            #
#  Utility functions — Sales Menu (Session 16)                                 #
# --------------------------------------------------------------------------- #


def _calculer_datetime_ouverture_service():
    """
    Calcule le debut du service en cours : 1ere LigneArticle VALID
    apres la derniere cloture journaliere.
    Retourne None si aucune vente depuis la derniere cloture.
    / Computes the start of the current shift: 1st VALID LigneArticle
    after the last daily closure.
    Returns None if no sales since the last closure.

    LOCALISATION : laboutik/views.py

    Logique identique a cloturer() lignes 947-979.
    / Same logic as cloturer() lines 947-979.
    """
    # La cloture est globale au tenant (pas par PV)
    # / Closure is global to the tenant (not per POS)
    derniere_cloture = (
        ClotureCaisse.objects.filter(
            niveau=ClotureCaisse.JOURNALIERE,
        )
        .order_by("-datetime_cloture")
        .first()
    )

    if derniere_cloture:
        premiere_vente = (
            LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
                status=LigneArticle.VALID,
                datetime__gt=derniere_cloture.datetime_cloture,
            )
            .order_by("datetime")
            .first()
        )
    else:
        premiere_vente = (
            LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
                status=LigneArticle.VALID,
            )
            .order_by("datetime")
            .first()
        )

    if not premiere_vente:
        return None

    return premiere_vente.datetime


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

    # URL de retour vers l'interface POS
    # / Return URL to the POS interface
    url_retour_pv = reverse("laboutik-caisse-point_de_vente")
    if uuid_pv:
        url_retour_pv += f"?uuid_pv={uuid_pv}&tag_id_cm={tag_id_cm}"

    # Params a propager dans toutes les URLs HTMX des vues Ventes
    # / Params to propagate in all HTMX URLs of Sales views
    params_ventes = f"uuid_pv={uuid_pv}&tag_id_cm={tag_id_cm}" if uuid_pv else ""

    laboutik_config = LaboutikConfiguration.get_solo()

    # state et stateJson : necessaires pour base.html (JS init)
    # Un state minimal suffit pour les vues Ventes (pas de NFC, pas de panier)
    # / state and stateJson: needed for base.html (JS init)
    # A minimal state is enough for Sales views (no NFC, no cart)
    state = _construire_state()

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
# / Asset category → PaymentMethod mapping for LigneArticle.
MAPPING_ASSET_CATEGORY_PAYMENT_METHOD = {
    Asset.TNF: PaymentMethod.LOCAL_GIFT,  # LG — cadeau
    Asset.TLF: PaymentMethod.LOCAL_EURO,  # LE — monnaie locale
    Asset.FED: PaymentMethod.LOCAL_EURO,  # LE — fédéré (assimilé local)
    Asset.TIM: PaymentMethod.LOCAL_EURO,  # LE — temps
    Asset.FID: PaymentMethod.LOCAL_EURO,  # LE — fidélité
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
            # Lignes intermédiaires : proportionnel, arrondi 6 décimales
            # / Intermediate lines: proportional, rounded to 6 decimal places
            qty_proportionnelle = (
                qty_totale
                * Decimal(ligne["amount_centimes"])
                / Decimal(prix_unitaire_centimes)
            ).quantize(SIX_DECIMALES)
            ligne["qty"] = qty_proportionnelle
            somme_qty_precedentes += qty_proportionnelle

    return lignes_avec_amounts


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

    # Charger tous les produits du PV en une seule requête (avec prix EUR préchargés)
    # Load all PV products in a single query (with EUR prices prefetched)
    prix_euros_prefetch = Prefetch(
        "prices",
        queryset=Price.objects.filter(publish=True, asset__isnull=True).order_by(
            "order"
        ),
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
        ).prefetch_related(prix_euros_prefetch)
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

        if produit is None:
            logger.warning(
                f"Produit {uuid_str} non trouvé dans le PV {point_de_vente.name}"
            )
            continue

        if not produit.prix_euros:
            logger.warning(f"Produit {produit.name} n'a pas de prix EUR publié")
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
        # Le custom_amount est accepte pour : prix libre (free_price) ET poids/mesure (poids_mesure).
        # Pour le prix libre : le montant doit etre >= au minimum (prix de base).
        # Pour le poids/mesure : le montant est calcule cote JS (quantite x prix unitaire), pas de minimum.
        # Securite : rejeter les montants invalides pour les prix libres.
        # / Validate free price or weight/volume (custom_amount_centimes)
        # custom_amount accepted for: free price (free_price) AND weight/volume (poids_mesure).
        # Free price: amount must be >= minimum (base price).
        # Weight/volume: amount computed by JS (quantity x unit price), no minimum check.
        # Security: reject invalid amounts for free prices.
        if custom_amount_centimes is not None:
            if prix_obj.poids_mesure:
                # Poids/mesure : le montant est calcule par le JS, on l'accepte tel quel.
                # Verification de coherence : le montant doit etre > 0.
                # / Weight/volume: amount computed by JS, accepted as-is.
                # Sanity check: amount must be > 0.
                if custom_amount_centimes <= 0:
                    logger.warning(
                        f"Montant poids/mesure invalide ({custom_amount_centimes}) "
                        f"pour {prix_obj.name}"
                    )
                    custom_amount_centimes = None
            elif prix_obj.free_price:
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

    :param point_de_vente: instance PointDeVente
    :param articles_panier: liste de dicts retournée par _extraire_articles_du_panier() (optionnel)
    :return: liste de codes moyens de paiement (ex: ["nfc", "espece", "carte_bancaire"])
    """
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

    if point_de_vente.accepte_carte_bancaire:
        moyens.append("carte_bancaire")

    if point_de_vente.accepte_cheque:
        moyens.append("CH")

    return moyens


def _creer_lignes_articles(
    articles_panier,
    code_methode_paiement,
    asset_uuid=None,
    carte=None,
    wallet=None,
    uuid_transaction=None,
    point_de_vente=None,
):
    """
    Crée ProductSold, PriceSold et LigneArticle pour chaque article du panier.
    Creates ProductSold, PriceSold and LigneArticle for each article in the cart.

    LOCALISATION : laboutik/views.py

    Cette fonction est appelée dans un bloc transaction.atomic() par les fonctions
    de paiement (_payer_par_carte_ou_cheque, _payer_en_especes, _payer_par_nfc).
    This function is called inside a transaction.atomic() block by the payment
    functions (_payer_par_carte_ou_cheque, _payer_en_especes, _payer_par_nfc).

    :param articles_panier: liste de dicts retournée par _extraire_articles_du_panier()
    :param code_methode_paiement: code du moyen de paiement ("carte_bancaire", "espece", "CH", "nfc")
    :param asset_uuid: UUID de l'asset fedow_core (NFC uniquement, None pour espèces/CB)
    :param carte: CarteCashless (NFC uniquement, None pour espèces/CB)
    :param wallet: Wallet du client (NFC uniquement, None pour espèces/CB)
    :param point_de_vente: PointDeVente d'origine (nullable, pour ventilation CA par PV)
    :return: liste de LigneArticle créées
    """
    methode_db = MAPPING_CODES_PAIEMENT.get(
        code_methode_paiement, PaymentMethod.UNKNOWN
    )

    # Determiner l'origine de la vente selon le mode ecole (LNE exigence 5)
    # En mode ecole, les ventes sont marquees LABOUTIK_TEST et exclues des rapports.
    # / Determine sale origin based on training mode (LNE req. 5)
    # In training mode, sales are marked LABOUTIK_TEST and excluded from reports.
    laboutik_config_pour_mode = LaboutikConfiguration.get_solo()
    if laboutik_config_pour_mode.mode_ecole:
        sale_origin_pour_ligne = SaleOrigin.LABOUTIK_TEST
    else:
        sale_origin_pour_ligne = SaleOrigin.LABOUTIK

    lignes_creees = []

    # Accumulateur des produits dont le stock a été décrémenté.
    # On broadcastera la mise à jour via WebSocket après le commit.
    # / Accumulator of products whose stock was decremented.
    # We'll broadcast the update via WebSocket after commit.
    produits_stock_mis_a_jour = []

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

        # LigneArticle : ligne comptable de la vente
        # LigneArticle: accounting line of the sale
        ligne = LigneArticle.objects.create(
            pricesold=price_sold,
            qty=quantite,
            amount=prix_centimes,
            sale_origin=sale_origin_pour_ligne,
            payment_method=methode_db,
            status=LigneArticle.VALID,
            uuid_transaction=uuid_transaction,
            point_de_vente=point_de_vente,
            # Champs NFC (optionnels, None pour espèces/CB)
            # NFC fields (optional, None for cash/CC)
            asset=asset_uuid,
            carte=carte,
            wallet=wallet,
            weight_quantity=weight_amount,
        )
        # --- Décrémentation stock inventaire ---
        # Si le produit a un Stock lié, on décrémente automatiquement.
        # Après décrémentation, on relit le stock depuis la DB
        # (F() ne met pas à jour l'instance en mémoire).
        # / If the product has a linked Stock, auto-decrement.
        # After decrement, re-read stock from DB (F() doesn't update in-memory instance).
        try:
            stock_du_produit = produit.stock_inventaire
            from inventaire.services import StockService

            if weight_amount:
                # Poids/mesure : la quantite saisie par le caissier remplace contenance x qty.
                # On décrémente la quantité saisie (ex: 350g), pas la contenance fixe.
                # / Weight/volume: cashier's entered quantity replaces contenance x qty.
                # We decrement the entered quantity (e.g. 350g), not the fixed contenance.
                StockService.decrementer_pour_vente(
                    stock=stock_du_produit,
                    contenance=weight_amount,
                    qty=1,
                    ligne_article=ligne,
                )
            else:
                # Tarif classique : contenance fixe x quantite
                # / Standard price: fixed contenance x quantity
                StockService.decrementer_pour_vente(
                    stock=stock_du_produit,
                    contenance=prix_obj.contenance,
                    qty=quantite,
                    ligne_article=ligne,
                )

            # Relire le stock depuis la DB pour avoir la quantité à jour
            # / Re-read stock from DB to get updated quantity
            stock_du_produit.refresh_from_db()

            produits_stock_mis_a_jour.append(
                {
                    "product_uuid": str(produit.uuid),
                    "quantite": stock_du_produit.quantite,
                    "unite": stock_du_produit.unite,
                    "en_alerte": stock_du_produit.est_en_alerte(),
                    "en_rupture": stock_du_produit.est_en_rupture(),
                    "bloquant": (
                        stock_du_produit.est_en_rupture()
                        and not stock_du_produit.autoriser_vente_hors_stock
                    ),
                    "quantite_lisible": _formater_stock_lisible(
                        stock_du_produit.quantite, stock_du_produit.unite
                    ),
                }
            )
        except Exception:
            # Pas de stock géré pour ce produit — comportement normal
            # / No stock managed for this product — normal behavior
            pass

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
        # Calculer le HT (donnee elementaire LNE exigence 3)
        # / Compute HT (LNE req. 3 elementary data)
        ligne_a_chainer.total_ht = calculer_total_ht(
            ligne_a_chainer.amount, ligne_a_chainer.vat
        )

        # Chainer le HMAC avec la ligne precedente
        # / Chain HMAC with previous line
        ligne_a_chainer.previous_hmac = previous_hmac_value
        ligne_a_chainer.hmac_hash = calculer_hmac(
            ligne_a_chainer, cle_hmac, previous_hmac_value
        )
        ligne_a_chainer.save(update_fields=["total_ht", "hmac_hash", "previous_hmac"])

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

    return lignes_creees


def _creer_lignes_articles_cascade(
    lignes_pre_calculees,
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

    :param lignes_pre_calculees: liste de tuples
        (article_dict, asset_ou_none, amount_centimes, payment_method_code)
    :param carte: CarteCashless principale (1ère carte NFC)
    :param carte_complement: CarteCashless de complément (2ème carte, Task 7)
    :param wallet: Wallet du client (1ère carte)
    :param uuid_transaction: UUID partagé par toutes les lignes du paiement
    :param point_de_vente: PointDeVente d'origine (ventilation CA par PV)
    :return: liste de toutes les LigneArticle créées
    """
    # --- Déterminer le sale_origin (mode école LNE exigence 5) ---
    # / Determine sale_origin (training mode LNE req. 5)
    laboutik_config = LaboutikConfiguration.get_solo()
    if laboutik_config.mode_ecole:
        sale_origin_pour_ligne = SaleOrigin.LABOUTIK_TEST
    else:
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
                asset_uuid = asset_ou_none.pk

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

            ligne = LigneArticle.objects.create(
                pricesold=price_sold,
                qty=qty_partielle,
                amount=amount_centimes,
                sale_origin=sale_origin_pour_ligne,
                payment_method=payment_method_code,
                status=LigneArticle.VALID,
                uuid_transaction=uuid_transaction,
                point_de_vente=point_de_vente,
                # Champs NFC (optionnels, None pour espèces/CB)
                # NFC fields (optional, None for cash/CC)
                asset=asset_uuid,
                carte=carte_pour_cette_ligne,
                wallet=wallet,
                # weight_quantity identique sur toutes les lignes d'un même article
                # / weight_quantity same on all lines of the same article
                weight_quantity=weight_amount,
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
            from inventaire.services import StockService

            if weight_amount:
                # Poids/mesure : la quantité saisie remplace contenance x qty.
                # / Weight/volume: entered quantity replaces contenance x qty.
                StockService.decrementer_pour_vente(
                    stock=stock_du_produit,
                    contenance=weight_amount,
                    qty=1,
                    ligne_article=premiere_ligne_du_groupe,
                )
            else:
                # Tarif classique : contenance fixe x quantité totale
                # / Standard price: fixed contenance x total quantity
                StockService.decrementer_pour_vente(
                    stock=stock_du_produit,
                    contenance=prix_obj.contenance,
                    qty=quantite,
                    ligne_article=premiere_ligne_du_groupe,
                )

            # Relire le stock depuis la DB pour avoir la quantité à jour
            # / Re-read stock from DB to get updated quantity
            stock_du_produit.refresh_from_db()

            produits_stock_mis_a_jour.append(
                {
                    "product_uuid": str(produit.uuid),
                    "quantite": stock_du_produit.quantite,
                    "unite": stock_du_produit.unite,
                    "en_alerte": stock_du_produit.est_en_alerte(),
                    "en_rupture": stock_du_produit.est_en_rupture(),
                    "bloquant": (
                        stock_du_produit.est_en_rupture()
                        and not stock_du_produit.autoriser_vente_hors_stock
                    ),
                    "quantite_lisible": _formater_stock_lisible(
                        stock_du_produit.quantite, stock_du_produit.unite
                    ),
                }
            )
        except Exception:
            # Pas de stock géré pour ce produit — comportement normal
            # / No stock managed for this product — normal behavior
            pass

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
        # Calculer le HT (donnée élémentaire LNE exigence 3)
        # / Compute HT (LNE req. 3 elementary data)
        ligne_a_chainer.total_ht = calculer_total_ht(
            ligne_a_chainer.amount, ligne_a_chainer.vat
        )

        # Chaîner le HMAC avec la ligne précédente
        # / Chain HMAC with previous line
        ligne_a_chainer.previous_hmac = previous_hmac_value
        ligne_a_chainer.hmac_hash = calculer_hmac(
            ligne_a_chainer, cle_hmac, previous_hmac_value
        )
        ligne_a_chainer.save(update_fields=["total_ht", "hmac_hash", "previous_hmac"])

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

    return toutes_les_lignes_creees


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
        # Renouveler : mettre à jour la date de contribution et recalculer la deadline
        # Renew: update contribution date and recalculate deadline
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
        membership_existante.set_deadline()
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
    nouvelle_adhesion.set_deadline()
    return nouvelle_adhesion


def _creer_adhesions_depuis_panier(request, articles_panier, lignes_articles=None):
    """
    Cree les Memberships pour les articles adhesion du panier (CB/especes).
    Rattache chaque Membership a sa LigneArticle correspondante (FK membership).
    Creates Memberships for membership articles in the cart (card/cash).
    Links each Membership to its corresponding LigneArticle (FK membership).

    LOCALISATION : laboutik/views.py

    Identification du client par :
    1. Scan NFC (tag_id dans le POST) → carte.user
    2. Formulaire email/nom/prenom (email_adhesion dans le POST) → get_or_create_user

    :param request: HttpRequest (pour lire le POST)
    :param articles_panier: liste de dicts retournee par _extraire_articles_du_panier()
    :param lignes_articles: liste de LigneArticle creees par _creer_lignes_articles() (pour rattacher membership)
    :return: liste de Membership creees
    """
    from decimal import Decimal

    articles_adhesion = [
        a for a in articles_panier if a["product"].categorie_article == Product.ADHESION
    ]
    if not articles_adhesion:
        return []

    user_adhesion = None
    carte_client = None

    # Option 1 : identification par scan NFC
    # / Option 1: identification by NFC scan
    tag_id_client = request.POST.get("tag_id", "").upper().strip()
    if tag_id_client:
        try:
            carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
            user_adhesion = carte_client.user
        except CarteCashless.DoesNotExist:
            logger.warning(f"Carte NFC {tag_id_client} introuvable pour adhesion")

    # Option 2 : identification par formulaire email/nom/prenom
    # / Option 2: identification by email/name form
    email_client = request.POST.get("email_adhesion", "").strip().lower()
    if email_client and user_adhesion is None:
        user_adhesion = get_or_create_user(email_client, send_mail=False)

    if user_adhesion is None:
        # REFUS : pas d'identification → pas d'adhesion (validation serveur obligatoire)
        # REJECT: no identification → no membership (mandatory server-side validation)
        raise ValueError(_("Identification du membre obligatoire pour les adhesions"))

    # Fusion wallet ephemere → wallet user (si carte NFC scannee)
    # / Merge ephemeral wallet → user wallet (if NFC card was scanned)
    if tag_id_client and carte_client:
        WalletService.fusionner_wallet_ephemere(
            carte=carte_client,
            user=user_adhesion,
            tenant=connection.tenant,
            ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
        )

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

    return memberships_creees


def imprimer_billet(ticket, reservation, event, pv):
    """
    Lance l'impression asynchrone d'un billet via Celery.
    Si le point de vente n'a pas d'imprimante configuree, on log sans erreur.
    / Launches asynchronous ticket printing via Celery.
    If the point of sale has no configured printer, logs without error.

    LOCALISATION : laboutik/views.py

    :param ticket: BaseBillet.Ticket
    :param reservation: BaseBillet.Reservation
    :param event: BaseBillet.Event
    :param pv: laboutik.PointDeVente (pour recuperer l'imprimante)
    """
    # Verifier que le PV a une imprimante configuree
    # / Check that the POS has a configured printer
    if not pv or not pv.printer or not pv.printer.active:
        logger.info(
            f"[PRINT] Pas d'imprimante active pour le PV "
            f"'{pv.name if pv else 'None'}' — billet {ticket.uuid} non imprime"
        )
        return

    from laboutik.printing.formatters import formatter_ticket_billet
    from laboutik.printing.tasks import imprimer_async

    ticket_data = formatter_ticket_billet(ticket, reservation, event)

    imprimer_async.delay(
        str(pv.printer.pk),
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
    7. Appelle imprimer_billet() → Celery async (si imprimante configuree)

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

    # --- Recuperer le point de vente pour l'impression ---
    # / Get the point of sale for printing
    pv = None
    uuid_pv = request.POST.get("uuid_pv", "")
    if uuid_pv:
        try:
            pv = PointDeVente.objects.select_related("printer").get(uuid=uuid_pv)
        except (PointDeVente.DoesNotExist, ValueError):
            pass

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
                imprimer_billet(ticket, reservation, event_locked, pv)

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
    articles_panier, wallet_client, carte_client, code_methode_paiement, ip_client
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
        )


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

        state = _construire_state(point_de_vente)

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

        # Mode gérant : activé si la carte primaire est en mode édition
        # Manager mode: enabled if primary card is in edit mode
        est_mode_gerant = False

        # Une consigne dans le panier déclenche un flux de remboursement
        # A deposit in the basket triggers a refund flow
        uuids_articles_selectionnes = payment_method.extraire_uuids_articles(
            request.POST
        )
        consigne_dans_panier = UUID_ARTICLE_CONSIGNE in uuids_articles_selectionnes
        if consigne_dans_panier:
            total_en_euros = abs(total_en_euros)

        context = {
            "state": state,
            "moyens_paiement": moyens_paiement_disponibles,
            "moyens_paiement_csv": moyens_paiement_csv,
            "currency_data": CURRENCY_DATA,
            "total": total_en_euros,
            "mode_gerant": est_mode_gerant,
            "deposit_is_present": consigne_dans_panier,
            "comportement": point_de_vente.comportement,
            "panier_a_recharges": panier_a_recharges,
            "panier_a_adhesions": panier_a_adhesions,
            "panier_a_billets": panier_a_billets,
            "panier_necessite_client": panier_necessite_client,
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

        context = {
            "method": moyen_paiement_choisi,
            "total": total_a_payer,
            "payment_translation": PAYMENT_METHOD_TRANSLATIONS.get(
                moyen_paiement_choisi, ""
            ),
            "uuid_transaction": uuid_transaction,
            "currency_data": CURRENCY_DATA,
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

        state = _construire_state(point_de_vente)

        # --- Normaliser les montants (les champs texte du formulaire → entiers) ---
        # --- Normalize amounts (form text fields → integers) ---
        donnees_paiement["total"] = int(donnees_paiement.get("total", 0))
        somme_donnee_brute = donnees_paiement.get("given_sum", "")
        if somme_donnee_brute == "":
            donnees_paiement["given_sum"] = 0
        else:
            donnees_paiement["given_sum"] = int(somme_donnee_brute)
        donnees_paiement["missing"] = 0

        # --- Extraire les articles du panier depuis la DB ---
        # --- Extract cart articles from DB ---
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

        # --- Calculer le total en centimes ---
        # --- Calculate total in centimes ---
        uuids_articles_selectionnes = payment_method.extraire_uuids_articles(
            request.POST
        )
        consigne_dans_panier = UUID_ARTICLE_CONSIGNE in uuids_articles_selectionnes
        total_centimes = _calculer_total_panier_centimes(articles_panier)
        total_en_euros = total_centimes / 100
        if consigne_dans_panier:
            total_en_euros = abs(total_en_euros)
            total_centimes = abs(total_centimes)

        # --- Transaction précédente (complément après fonds insuffisants) ---
        # --- Previous transaction (top-up after insufficient funds) ---
        # Phase 3 : sera implémenté avec fedow_core
        # Phase 3: will be implemented with fedow_core
        transaction_precedente = None

        # --- Aiguillage vers le bon flux de paiement ---
        # --- Route to the correct payment flow ---
        moyen_paiement_code = donnees_paiement.get("moyen_paiement", "")
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
            )

        # Moyen de paiement non reconnu → erreur
        # Unrecognized payment method → error
        context_erreur = {
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
        point_de_vente = PointDeVente.objects.select_related("printer").get(
            uuid=uuid_pv
        )

        # Identifiant unique de ce paiement — regroupe toutes les LigneArticle
        # / Unique ID for this payment — groups all LigneArticle records
        uuid_transaction = uuid_module.uuid4()

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

        with db_transaction.atomic():
            # Articles normaux (ventes, adhesions) → LigneArticle
            # Normal articles (sales, memberships) → LigneArticle
            lignes_normales = []
            if articles_normaux:
                lignes_normales = _creer_lignes_articles(
                    articles_normaux,
                    moyen_paiement_code,
                    uuid_transaction=uuid_transaction,
                    point_de_vente=point_de_vente,
                )

            # Adhesions → creer les Memberships et les rattacher aux LigneArticle
            # Memberships → create Membership records and link them to LigneArticle
            _creer_adhesions_depuis_panier(
                request, articles_normaux, lignes_articles=lignes_normales
            )

            # Billets → creer Reservation + Tickets et rattacher aux LigneArticle
            # Tickets → create Reservation + Tickets and link them to LigneArticle
            reservations_billets = _creer_billets_depuis_panier(
                request,
                articles_normaux,
                lignes_articles=lignes_normales,
            )

            # Recharges → TransactionService + LigneArticle avec carte et asset
            # Top-ups → TransactionService + LigneArticle with card and asset
            if articles_recharge:
                tag_id_client = request.POST.get("tag_id", "").upper().strip()
                if not tag_id_client:
                    raise ValueError(_("Tag NFC client requis pour les recharges"))

                carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
                wallet_client = _obtenir_ou_creer_wallet(carte_client)
                _executer_recharges(
                    articles_recharge,
                    wallet_client,
                    carte_client,
                    code_methode_paiement=moyen_paiement_code,
                    ip_client=ip_client,
                )

        # Apres le bloc atomic : envoyer les billets par email via Celery.
        # Ne pas appeler dans le bloc atomic (si rollback, le mail partirait quand meme).
        # / After the atomic block: send tickets by email via Celery.
        # Do not call inside the atomic block (if rollback, email would still be sent).
        if reservations_billets:
            _envoyer_billets_par_email(reservations_billets)

        # Impression automatique des billets pour le PV BILLETTERIE
        # / Auto-print tickets for ticketing POS
        if (
            reservations_billets
            and point_de_vente.comportement == PointDeVente.BILLETTERIE
            and point_de_vente.printer
            and point_de_vente.printer.active
        ):
            from BaseBillet.models import Ticket

            for reservation in reservations_billets:
                tickets_reservation = Ticket.objects.filter(
                    reservation=reservation,
                ).select_related("pricesold", "reservation__event")
                for ticket_obj in tickets_reservation:
                    imprimer_billet(
                        ticket_obj, reservation, reservation.event, point_de_vente
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
            "uuid_pv": str(point_de_vente.uuid),
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
        point_de_vente = PointDeVente.objects.select_related("printer").get(
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

            # Identifiant unique de ce paiement
            # / Unique ID for this payment
            uuid_transaction = uuid_module.uuid4()

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

            # Créer les lignes articles en base (atomique)
            # Create article lines in DB (atomic)
            with db_transaction.atomic():
                # Articles normaux (ventes, adhesions) → LigneArticle
                # Normal articles (sales, memberships) → LigneArticle
                lignes_normales = []
                if articles_normaux:
                    lignes_normales = _creer_lignes_articles(
                        articles_normaux,
                        moyen_paiement_code,
                        uuid_transaction=uuid_transaction,
                        point_de_vente=point_de_vente,
                    )

                # Adhesions → creer les Memberships et les rattacher aux LigneArticle
                # Memberships → create Membership records and link them to LigneArticle
                _creer_adhesions_depuis_panier(
                    request, articles_normaux, lignes_articles=lignes_normales
                )

                # Billets → creer Reservation + Tickets et rattacher aux LigneArticle
                # Tickets → create Reservation + Tickets and link them to LigneArticle
                reservations_billets = _creer_billets_depuis_panier(
                    request,
                    articles_normaux,
                    lignes_articles=lignes_normales,
                )

                # Recharges → TransactionService + LigneArticle avec carte et asset
                # Top-ups → TransactionService + LigneArticle with card and asset
                if articles_recharge:
                    tag_id_client = request.POST.get("tag_id", "").upper().strip()
                    if not tag_id_client:
                        raise ValueError(_("Tag NFC client requis pour les recharges"))

                    carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
                    wallet_client = _obtenir_ou_creer_wallet(carte_client)
                    _executer_recharges(
                        articles_recharge,
                        wallet_client,
                        carte_client,
                        code_methode_paiement=moyen_paiement_code,
                        ip_client=ip_client,
                    )

            # Apres le bloc atomic : envoyer les billets par email via Celery
            # / After the atomic block: send tickets by email via Celery
            if reservations_billets:
                _envoyer_billets_par_email(reservations_billets)

            # Impression automatique des billets pour le PV BILLETTERIE
            # / Auto-print tickets for ticketing POS
            if (
                reservations_billets
                and point_de_vente.comportement == PointDeVente.BILLETTERIE
                and point_de_vente.printer
                and point_de_vente.printer.active
            ):
                for reservation in reservations_billets:
                    tickets_reservation = Ticket.objects.filter(
                        reservation=reservation,
                    ).select_related("pricesold", "reservation__event")
                    for ticket_obj in tickets_reservation:
                        imprimer_billet(
                            ticket_obj, reservation, reservation.event, point_de_vente
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
                "uuid_pv": str(point_de_vente.uuid),
            }
            return render(
                request, "laboutik/partial/hx_return_payment_success.html", context
            )

        # Somme insuffisante → ne rien faire (le JS gère la validation côté client)
        # Insufficient amount → do nothing (JS handles client-side validation)
        context_erreur = {
            "msg_type": "warning",
            "msg_content": _("Il y a une erreur !"),
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context_erreur)

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
                "msg_type": "warning",
                "msg_content": _(
                    "Les recharges ne peuvent pas être payées en cashless"
                ),
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
                "msg_type": "warning",
                "msg_content": _("Carte inconnue"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur)

        # Déterminer le wallet client (get or create éphémère si besoin)
        # / Determine client wallet (get or create ephemeral if needed)
        wallet_client = _obtenir_ou_creer_wallet(carte_client)

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

        for article in articles_panier:
            produit = article["product"]
            prix_obj = article["price"]
            methode = produit.methode_caisse

            if produit.categorie_article == Product.ADHESION:
                # Les adhésions utilisent la cascade fiduciaire (pas de non-fidu)
                # / Memberships use fiduciary cascade (no non-fidu)
                articles_adhesion.append(article)
            elif methode in METHODES_RECHARGE_GRATUITES:
                # RC (cadeau) ou TM (temps) : crédit gratuit, pas de débit
                # / RC (gift) or TM (time): free credit, no debit
                articles_recharge_gratuite.append(article)
            elif (
                getattr(prix_obj, "non_fiduciaire", False)
                and prix_obj.asset is not None
            ):
                # Prix non-fiduciaire (TIM, FID) : débit direct sur l'asset du prix
                # / Non-fiduciary price (TIM, FID): direct debit on the price's asset
                articles_non_fiduciaires.append(article)
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
                "msg_type": "warning",
                "msg_content": _("Monnaie locale non configurée"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur)

        # ================================================================ #
        #  PHASE 3 : Vérifier soldes non-fiduciaires (tout ou rien)         #
        #  PHASE 3: Check non-fiduciary balances (all or nothing)           #
        # ================================================================ #

        for article_nf in articles_non_fiduciaires:
            asset_cible = article_nf["price"].asset
            montant_necessaire = article_nf["prix_centimes"] * article_nf["quantite"]
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
                    "monnaie_name": asset_cible.name,
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
                payment_method_pour_asset = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD.get(
                    asset_courant.category, PaymentMethod.LOCAL_EURO
                )
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
                "tag_id_carte1": tag_id_client,
                "detail_cascade": detail_cascade_affichage,
                "cascade_carte1_json": cascade_json,
                "total_nfc_carte1": total_nfc,
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
        uuid_transaction = uuid_module.uuid4()

        try:
            with db_transaction.atomic():
                # ----- 7a) Crédits recharges gratuites AVANT les débits -----
                # / Free top-up credits BEFORE debits
                if articles_recharge_gratuite:
                    _executer_recharges(
                        articles_recharge_gratuite,
                        wallet_client,
                        carte_client,
                        code_methode_paiement="gift",
                        ip_client=ip_client,
                    )

                # ----- 7b) Débits non-fiduciaires (direct sur asset du prix) -----
                # / Non-fiduciary debits (direct on the price's asset)
                lignes_non_fidu = []
                for article_nf in articles_non_fiduciaires:
                    asset_nf_cible = article_nf["price"].asset
                    montant_nf = article_nf["prix_centimes"] * article_nf["quantite"]
                    TransactionService.creer_vente(
                        sender_wallet=wallet_client,
                        receiver_wallet=asset_nf_cible.wallet_origin,
                        asset=asset_nf_cible,
                        montant_en_centimes=montant_nf,
                        tenant=tenant_courant,
                        card=carte_client,
                        ip=ip_client,
                    )
                    pm_nf = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD.get(
                        asset_nf_cible.category, PaymentMethod.LOCAL_EURO
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

                for asset_a_debiter, total_debit_asset in debits_par_asset.items():
                    TransactionService.creer_vente(
                        sender_wallet=wallet_client,
                        receiver_wallet=asset_a_debiter.wallet_origin,
                        asset=asset_a_debiter,
                        montant_en_centimes=total_debit_asset,
                        tenant=tenant_courant,
                        card=carte_client,
                        ip=ip_client,
                    )

                # ----- 7d) Créer toutes les LigneArticle (non-fidu + cascade) -----
                # / Create all LigneArticle (non-fidu + cascade)
                toutes_les_lignes_pre_calculees = lignes_non_fidu + lignes_nfc
                lignes_creees = _creer_lignes_articles_cascade(
                    lignes_pre_calculees=toutes_les_lignes_pre_calculees,
                    carte=carte_client,
                    wallet=wallet_client,
                    uuid_transaction=uuid_transaction,
                    point_de_vente=point_de_vente,
                )

                # ----- 7e) Adhésions : créer Membership, rattacher à la 1ère LigneArticle -----
                # / Memberships: create Membership, link to first LigneArticle
                if articles_adhesion:
                    # Construire index LigneArticle par product_uuid
                    # / Build LigneArticle index by product_uuid
                    lignes_par_product = {}
                    for ligne_creee in lignes_creees:
                        product_uuid_str = str(
                            ligne_creee.pricesold.productsold.product.uuid
                        )
                        if product_uuid_str not in lignes_par_product:
                            lignes_par_product[product_uuid_str] = ligne_creee

                    for article_ad in articles_adhesion:
                        membership = _creer_ou_renouveler_adhesion(
                            carte_client.user,
                            article_ad["product"],
                            article_ad["price"],
                        )
                        if membership:
                            product_uuid_ad = str(article_ad["product"].uuid)
                            ligne_ad = lignes_par_product.get(product_uuid_ad)
                            if ligne_ad:
                                ligne_ad.membership = membership
                                ligne_ad.save(update_fields=["membership"])

        except SoldeInsuffisant:
            # Race condition : solde a changé entre le check et le débit
            # / Race condition: balance changed between check and debit
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
                "monnaie_name": nom_monnaie_fallback,
                "payments_accepted": {
                    "accepte_especes": point_de_vente.accepte_especes,
                    "accepte_carte_bancaire": point_de_vente.accepte_carte_bancaire,
                },
                "uuid_transaction": "",
            }
            return render(
                request,
                "laboutik/partial/hx_funds_insufficient.html",
                context_insuffisant,
            )

        # ================================================================ #
        #  PHASE 8 : Succès — soldes multi-asset                            #
        #  PHASE 8: Success — multi-asset balances                          #
        # ================================================================ #

        # Lire les soldes de TOUS les assets débités (pas seulement TLF)
        # / Read balances of ALL debited assets (not just TLF)
        soldes_apres_paiement = []
        for asset_debite in assets_debites:
            solde_apres = WalletService.obtenir_solde(
                wallet=wallet_client, asset=asset_debite
            )
            soldes_apres_paiement.append(
                {
                    "name": asset_debite.name,
                    "solde_euros": solde_apres / 100,
                }
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

        context = {
            "currency_data": CURRENCY_DATA,
            "payment": donnees_paiement,
            "monnaie_name": nom_monnaie_principal,
            "moyen_paiement": PAYMENT_METHOD_TRANSLATIONS.get(moyen_paiement_code, ""),
            "deposit_is_present": consigne_dans_panier,
            "total": total_en_euros,
            "state": state,
            "original_payment": None,
            # Données spécifiques NFC / NFC-specific data
            "nouveau_solde": nouveau_solde_euros,
            "card_name": carte_client.tag_id,
            "uuid_transaction": str(uuid_transaction),
            "uuid_pv": str(point_de_vente.uuid),
            # Multi-asset : liste des soldes après paiement
            # / Multi-asset: list of balances after payment
            "soldes_apres_paiement": soldes_apres_paiement,
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
        - Si user identifie → hx_recapitulatif_client.html (resume articles + boutons paiement)
        - Si carte anonyme → hx_formulaire_identification_client.html (pre-rempli avec tag_id)
        - Si formulaire soumis avec email → validation puis hx_recapitulatif_client.html

        Receives tag_id (NFC scan) OR email/name (form).
        POST also contains repid-* (cart articles) and uuid_pv,
        because the submitted form is #addition-form (which contains everything).

        Returns:
        - If user identified → hx_recapitulatif_client.html (article recap + payment buttons)
        - If anonymous card → hx_formulaire_identification_client.html (pre-filled with tag_id)
        - If form submitted with email → validation then hx_recapitulatif_client.html

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
                _executer_recharges(
                    articles_panier,
                    wallet_client,
                    carte,
                    code_methode_paiement="gift",
                    ip_client=ip_client,
                )

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
                "total": total_en_euros,
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

            # Enrichir les articles avec un texte adaptatif par type
            # / Enrich articles with adaptive text per type
            articles_pour_recapitulatif = _construire_recapitulatif_articles(
                articles_panier,
                user_prenom,
                user_nom,
            )

            context = {
                "user_email": user.email,
                "user_prenom": user_prenom,
                "user_nom": user_nom,
                "user_solde": solde,
                "tag_id": tag_id,
                "moyens_paiement": moyens_paiement,
                "panier_a_recharges": panier_a_recharges,
                "panier_a_adhesions": panier_a_adhesions,
                "panier_a_billets": panier_a_billets,
                "articles_pour_recapitulatif": articles_pour_recapitulatif,
                "total_en_euros": total_en_euros,
            }
            return render(
                request, "laboutik/partial/hx_recapitulatif_client.html", context
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

            carte_label = carte.tag_id
            articles_pour_recapitulatif = _construire_recapitulatif_articles(
                articles_panier,
                carte_label,
                "",
            )

            context = {
                "user_email": "",
                "user_prenom": _("Carte anonyme"),
                "user_nom": carte.tag_id,
                "user_solde": solde_carte,
                "tag_id": tag_id,
                "moyens_paiement": moyens_paiement,
                "panier_a_recharges": panier_a_recharges,
                "panier_a_adhesions": panier_a_adhesions,
                "panier_a_billets": panier_a_billets,
                "articles_pour_recapitulatif": articles_pour_recapitulatif,
                "total_en_euros": total_en_euros,
            }
            return render(
                request, "laboutik/partial/hx_recapitulatif_client.html", context
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
                "msg_type": "warning",
                "msg_content": str(e),
                "selector_bt_retour": "#messages",
            }
            return render(
                request, "laboutik/partial/hx_messages.html", context_erreur, status=400
            )

        total_centimes = _calculer_total_panier_centimes(articles_panier)
        state = _construire_state(point_de_vente)

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
                payment_method_pour_asset = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD.get(
                    asset_courant.category, PaymentMethod.LOCAL_EURO
                )
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
        uuid_transaction = uuid_module.uuid4()

        donnees_paiement["total"] = total_centimes
        donnees_paiement["given_sum"] = 0
        donnees_paiement["missing"] = 0

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

            try:
                with db_transaction.atomic():
                    # 6a) Recharges gratuites
                    # / 6a) Free top-ups
                    if articles_recharge_gratuite:
                        _executer_recharges(
                            articles_recharge_gratuite,
                            wallet_carte1,
                            carte1,
                            code_methode_paiement="gift",
                            ip_client=ip_client,
                        )

                    # 6b) Débits non-fiduciaires
                    # / 6b) Non-fiduciary debits
                    lignes_non_fidu = []
                    for article_nf in articles_non_fiduciaires:
                        asset_nf_cible = article_nf["price"].asset
                        montant_nf = (
                            article_nf["prix_centimes"] * article_nf["quantite"]
                        )
                        TransactionService.creer_vente(
                            sender_wallet=wallet_carte1,
                            receiver_wallet=asset_nf_cible.wallet_origin,
                            asset=asset_nf_cible,
                            montant_en_centimes=montant_nf,
                            tenant=tenant_courant,
                            card=carte1,
                            ip=ip_client,
                        )
                        pm_nf = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD.get(
                            asset_nf_cible.category, PaymentMethod.LOCAL_EURO
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

                    for (
                        asset_a_debiter,
                        total_debit_asset,
                    ) in debits_par_asset_c1.items():
                        TransactionService.creer_vente(
                            sender_wallet=wallet_carte1,
                            receiver_wallet=asset_a_debiter.wallet_origin,
                            asset=asset_a_debiter,
                            montant_en_centimes=total_debit_asset,
                            tenant=tenant_courant,
                            card=carte1,
                            ip=ip_client,
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

                    toutes_les_lignes = lignes_non_fidu + lignes_finales
                    lignes_creees = _creer_lignes_articles_cascade(
                        lignes_pre_calculees=toutes_les_lignes,
                        carte=carte1,
                        wallet=wallet_carte1,
                        uuid_transaction=uuid_transaction,
                        point_de_vente=point_de_vente,
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

            except SoldeInsuffisant:
                context_erreur = {
                    "msg_type": "warning",
                    "msg_content": _(
                        "Solde insuffisant. Le solde a changé depuis la lecture."
                    ),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request, "laboutik/partial/hx_messages.html", context_erreur
                )

            # ---------------------------------------------------------- #
            # Succès espèces/CB → affichage
            # / Cash/CC success → display
            # ---------------------------------------------------------- #
            soldes_apres_paiement = []
            for asset_debite in assets_debites:
                solde_apres = WalletService.obtenir_solde(
                    wallet=wallet_carte1, asset=asset_debite
                )
                soldes_apres_paiement.append(
                    {
                        "name": asset_debite.name,
                        "solde_euros": solde_apres / 100,
                    }
                )

            nouveau_solde_euros = None
            nom_monnaie_principal = ""
            if soldes_apres_paiement:
                nouveau_solde_euros = soldes_apres_paiement[0]["solde_euros"]
                nom_monnaie_principal = soldes_apres_paiement[0]["name"]

            context_succes = {
                "currency_data": CURRENCY_DATA,
                "payment": donnees_paiement,
                "monnaie_name": nom_monnaie_principal,
                "moyen_paiement": _("NFC"),
                "original_payment": True,
                "original_moyen_paiement": _("NFC"),
                "deposit_is_present": False,
                "total": total_centimes / 100,
                "state": state,
                "nouveau_solde": nouveau_solde_euros,
                "card_name": carte1.tag_id,
                "uuid_transaction": str(uuid_transaction),
                "uuid_pv": str(point_de_vente.uuid),
                "soldes_apres_paiement": soldes_apres_paiement,
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
            tag_id_carte2 = request.POST.get("tag_id", "").upper().strip()

            if not tag_id_carte2:
                context_erreur = {
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
                    "msg_type": "warning",
                    "msg_content": _("Carte 2 inconnue"),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request, "laboutik/partial/hx_messages.html", context_erreur
                )

            wallet_carte2 = _obtenir_ou_creer_wallet(carte2)

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
                    pm_c2 = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD.get(
                        asset_c2.category, PaymentMethod.LOCAL_EURO
                    )
                    lignes_nfc_carte2.append((art_c, asset_c2, debit_c2, pm_c2))
                    soldes_restants_c2[asset_c2] -= debit_c2
                    reste_complement -= debit_c2
                    assets_debites_carte2.add(asset_c2)

                if reste_complement > 0:
                    total_reste_apres_carte2 += reste_complement
                    lignes_nfc_carte2.append((art_c, None, reste_complement, None))

            if total_reste_apres_carte2 > 0:
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

                context_complement = {
                    "tag_id_carte1": tag_id_carte1,
                    "detail_cascade": detail_cascade_affichage,
                    "cascade_carte1_json": cascade_json_rerender,
                    "total_nfc_carte1": sum(debits_affichage_c1.values()),
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

            # Carte2 couvre tout le reste → bloc atomic
            # / Card2 covers all remainder → atomic block
            try:
                with db_transaction.atomic():
                    # Recharges gratuites
                    # / Free top-ups
                    if articles_recharge_gratuite:
                        _executer_recharges(
                            articles_recharge_gratuite,
                            wallet_carte1,
                            carte1,
                            code_methode_paiement="gift",
                            ip_client=ip_client,
                        )

                    # Débits non-fiduciaires carte1
                    # / Card1 non-fiduciary debits
                    lignes_non_fidu = []
                    for article_nf in articles_non_fiduciaires:
                        asset_nf_cible = article_nf["price"].asset
                        montant_nf = (
                            article_nf["prix_centimes"] * article_nf["quantite"]
                        )
                        TransactionService.creer_vente(
                            sender_wallet=wallet_carte1,
                            receiver_wallet=asset_nf_cible.wallet_origin,
                            asset=asset_nf_cible,
                            montant_en_centimes=montant_nf,
                            tenant=tenant_courant,
                            card=carte1,
                            ip=ip_client,
                        )
                        pm_nf = MAPPING_ASSET_CATEGORY_PAYMENT_METHOD.get(
                            asset_nf_cible.category, PaymentMethod.LOCAL_EURO
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

                    for (
                        asset_a_debiter,
                        total_debit_asset,
                    ) in debits_par_asset_c1.items():
                        TransactionService.creer_vente(
                            sender_wallet=wallet_carte1,
                            receiver_wallet=asset_a_debiter.wallet_origin,
                            asset=asset_a_debiter,
                            montant_en_centimes=total_debit_asset,
                            tenant=tenant_courant,
                            card=carte1,
                            ip=ip_client,
                        )

                    # Débits cascade carte2
                    # / Card2 cascade debits
                    debits_par_asset_c2 = OrderedDict()
                    for _art_c2, asset_c2, amount_c2, _pm_c2 in lignes_nfc_carte2:
                        if asset_c2 is not None:
                            if asset_c2 not in debits_par_asset_c2:
                                debits_par_asset_c2[asset_c2] = 0
                            debits_par_asset_c2[asset_c2] += amount_c2

                    for (
                        asset_a_debiter_c2,
                        total_debit_c2,
                    ) in debits_par_asset_c2.items():
                        TransactionService.creer_vente(
                            sender_wallet=wallet_carte2,
                            receiver_wallet=asset_a_debiter_c2.wallet_origin,
                            asset=asset_a_debiter_c2,
                            montant_en_centimes=total_debit_c2,
                            tenant=tenant_courant,
                            card=carte2,
                            ip=ip_client,
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

                    toutes_les_lignes = (
                        lignes_non_fidu + lignes_couvertes_c1 + lignes_couvertes_c2
                    )
                    lignes_creees = _creer_lignes_articles_cascade(
                        lignes_pre_calculees=toutes_les_lignes,
                        carte=carte1,
                        carte_complement=carte2,
                        wallet=wallet_carte1,
                        uuid_transaction=uuid_transaction,
                        point_de_vente=point_de_vente,
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

            except SoldeInsuffisant:
                context_erreur = {
                    "msg_type": "warning",
                    "msg_content": _(
                        "Solde insuffisant. Le solde a changé depuis la lecture."
                    ),
                    "selector_bt_retour": "#messages",
                }
                return render(
                    request, "laboutik/partial/hx_messages.html", context_erreur
                )

            # Succès 2ème carte → affichage multi-soldes
            # / 2nd card success → multi-balance display
            soldes_apres_paiement = []
            for asset_debite in assets_debites:
                solde_apres = WalletService.obtenir_solde(
                    wallet=wallet_carte1, asset=asset_debite
                )
                soldes_apres_paiement.append(
                    {
                        "name": f"{asset_debite.name} ({tag_id_carte1})",
                        "solde_euros": solde_apres / 100,
                    }
                )
            for asset_debite_c2 in assets_debites_carte2:
                solde_apres_c2 = WalletService.obtenir_solde(
                    wallet=wallet_carte2, asset=asset_debite_c2
                )
                soldes_apres_paiement.append(
                    {
                        "name": f"{asset_debite_c2.name} ({tag_id_carte2})",
                        "solde_euros": solde_apres_c2 / 100,
                    }
                )

            nouveau_solde_euros = None
            nom_monnaie_principal = ""
            if soldes_apres_paiement:
                nouveau_solde_euros = soldes_apres_paiement[0]["solde_euros"]
                nom_monnaie_principal = soldes_apres_paiement[0]["name"]

            context_succes = {
                "currency_data": CURRENCY_DATA,
                "payment": donnees_paiement,
                "monnaie_name": nom_monnaie_principal,
                "moyen_paiement": _("NFC"),
                "original_payment": None,
                "deposit_is_present": False,
                "total": total_centimes / 100,
                "state": state,
                "nouveau_solde": nouveau_solde_euros,
                "card_name": carte1.tag_id,
                "uuid_transaction": str(uuid_transaction),
                "uuid_pv": str(point_de_vente.uuid),
                "soldes_apres_paiement": soldes_apres_paiement,
            }
            return render(
                request,
                "laboutik/partial/hx_return_payment_success.html",
                context_succes,
            )

        # Moyen de complément non reconnu
        # / Unrecognized complement method
        context_erreur = {
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
        state = _construire_state()
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

        # 2. Déterminer le wallet (get or create éphémère si besoin)
        # 2. Determine the wallet (get or create ephemeral if needed)
        wallet = _obtenir_ou_creer_wallet(carte)

        # 3. Vrais soldes depuis fedow_core
        # 3. Real balances from fedow_core
        tokens_qs = WalletService.obtenir_tous_les_soldes(wallet)

        # Préparer les données pour le template (centimes → euros)
        # Prepare data for the template (cents → euros)
        tokens = []
        total_centimes = 0
        solde_tlf_centimes = 0
        solde_tnf_centimes = 0
        for t in tokens_qs:
            tokens.append(
                {
                    "asset_name": t.asset.name,
                    "asset_category": t.asset.category,
                    "value_euros": t.value / 100,
                    "provenance": t.asset.tenant_origin.name,
                }
            )
            total_centimes += t.value
            if t.asset.category == Asset.TLF:
                solde_tlf_centimes += t.value
            elif t.asset.category == Asset.TNF:
                solde_tnf_centimes += t.value

        # 4. Adhésions actives (si user connu)
        # 4. Active memberships (if user known)
        adhesions = []
        if carte.user:
            toutes_adhesions = list(
                Membership.objects.filter(
                    user=carte.user,
                )
                .exclude(
                    status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED],
                )
                .select_related("price__product")
            )
            adhesions = [m for m in toutes_adhesions if m.is_valid()]

        # 5. Couleur de fond selon le type de carte
        # 5. Background color based on card type
        email_carte = carte.user.email if carte.user else None
        prenom_carte = carte.user.first_name if carte.user else None
        couleur_fond = "--success" if email_carte else "--warning"

        context = {
            "card": {"email": email_carte, "first_name": prenom_carte},
            "total_monnaie": total_centimes / 100,
            "solde_tlf": solde_tlf_centimes / 100,
            "solde_tnf": solde_tnf_centimes / 100,
            "tokens": tokens,
            "adhesions": adhesions,
            "tag_id": tag_id_scanne,
            "background": couleur_fond,
            "state": state,
        }
        return render(request, "laboutik/partial/hx_card_feedback.html", context)

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
            request, "laboutik/partial/hx_vider_carte_overlay.html", contexte,
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
        Calcule les tokens eligibles pour la carte client scannee et renvoie
        l'overlay de confirmation. Pas de mutation DB.
        / Computes eligible tokens for the scanned client card and returns
        the confirmation overlay. No DB mutation.
        """
        from django.db.models import Q
        from fedow_core.models import Asset, Token

        tag_id = request.POST.get("tag_id", "").strip().upper()
        tag_id_cm = request.POST.get("tag_id_cm", "").strip().upper()
        uuid_pv = request.POST.get("uuid_pv", "")

        # Protection self-refund.
        if tag_id and tag_id == tag_id_cm:
            return _render_erreur_toast(
                request, _("Ne peut pas vider une carte primaire."),
            )

        try:
            carte = CarteCashless.objects.get(tag_id=tag_id)
        except CarteCashless.DoesNotExist:
            return _render_erreur_toast(request, _("Carte client inconnue."))

        wallet = _obtenir_ou_creer_wallet(carte)
        if wallet is None:
            return _render_erreur_toast(request, _("Carte vierge."))

        tokens = list(
            Token.objects.filter(
                wallet=wallet, value__gt=0,
            ).filter(
                Q(asset__category=Asset.TLF, asset__tenant_origin=connection.tenant)
                | Q(asset__category=Asset.FED)
            ).select_related('asset', 'asset__tenant_origin').order_by('asset__category')
        )

        if not tokens:
            return _render_erreur_toast(
                request, _("Aucun solde remboursable sur cette carte."),
            )

        total_tlf = sum(t.value for t in tokens if t.asset.category == Asset.TLF)
        total_fed = sum(t.value for t in tokens if t.asset.category == Asset.FED)

        contexte = {
            "carte": carte,
            "tokens": tokens,
            "total_centimes": total_tlf + total_fed,
            "total_tlf_centimes": total_tlf,
            "total_fed_centimes": total_fed,
            "tag_id": tag_id,
            "tag_id_cm": tag_id_cm,
            "uuid_pv": uuid_pv,
        }
        return render(
            request, "laboutik/partial/hx_vider_carte_confirm.html", contexte,
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
        Execute le remboursement via WalletService.rembourser_en_especes.
        Renvoie l'ecran de succes ou un toast d'erreur.
        / Executes the refund via WalletService.rembourser_en_especes.
        Returns the success screen or an error toast.
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
                request, _("Ne peut pas vider une carte primaire."),
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
                request, _("Cette carte caissier n'a pas acces a ce PV."),
            )

        receiver_wallet = WalletService.get_or_create_wallet_tenant(connection.tenant)

        try:
            resultat = WalletService.rembourser_en_especes(
                carte=carte_client,
                tenant=connection.tenant,
                receiver_wallet=receiver_wallet,
                ip=request.META.get("REMOTE_ADDR", "0.0.0.0"),
                vider_carte=vider_carte_flag,
                primary_card=carte_primaire_obj.carte,
            )
        except NoEligibleTokens:
            return _render_erreur_toast(
                request, _("Aucun solde remboursable (solde a pu changer)."),
            )

        contexte = {
            "total_centimes": resultat["total_centimes"],
            "total_tlf_centimes": resultat["total_tlf_centimes"],
            "total_fed_centimes": resultat["total_fed_centimes"],
            "lignes_articles": resultat["lignes_articles"],
            "transaction_uuids": [str(tx.uuid) for tx in resultat["transactions"]],
            "uuid_pv": uuid_pv,
            "vider_carte": vider_carte_flag,
        }
        return render(
            request, "laboutik/partial/hx_vider_carte_success.html", contexte,
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
        Lance l'impression Celery du recu pour les transactions_uuids donnees.
        / Launches the Celery receipt print for the given transaction UUIDs.
        """
        transaction_uuids = request.POST.getlist("transaction_uuids")
        uuid_pv = request.POST.get("uuid_pv", "")

        if not transaction_uuids or not uuid_pv:
            return _render_erreur_toast(request, _("Parametres manquants."))

        pv = PointDeVente.objects.select_related("printer").filter(uuid=uuid_pv).first()
        if pv is None or pv.printer is None or not pv.printer.active:
            return _render_erreur_toast(
                request, _("Pas d'imprimante configuree sur ce PV."),
            )

        transactions = Transaction.objects.filter(
            uuid__in=transaction_uuids,
        ).select_related("asset")

        from laboutik.printing.formatters import formatter_recu_vider_carte
        from laboutik.printing.tasks import imprimer_async

        recu_data = formatter_recu_vider_carte(list(transactions))
        imprimer_async.delay(
            str(pv.printer.pk),
            recu_data,
            connection.schema_name,
        )
        return render(request, "laboutik/partial/hx_impression_ok.html")

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
        Imprime (ou re-imprime) un ticket de vente a partir du uuid_transaction.
        Toutes les LigneArticle partageant ce uuid_transaction sont regroupees
        sur un seul ticket.
        / Prints (or reprints) a sale ticket from the uuid_transaction.
        All LigneArticle sharing this uuid_transaction are grouped on one ticket.

        LOCALISATION : laboutik/views.py

        FLUX :
        1. Recoit uuid_transaction et uuid_pv en POST
        2. Recupere le PV et son imprimante
        3. Recupere les LigneArticle de la transaction
        4. Formate le ticket via formatter_ticket_vente
        5. Lance l'impression async via Celery
        6. Retourne un partial HTML de confirmation
        """
        uuid_transaction_str = request.POST.get("uuid_transaction")
        uuid_pv = request.POST.get("uuid_pv")

        if not uuid_transaction_str or not uuid_pv:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Donnees manquantes pour l'impression"),
                    "selector_bt_retour": "#print-feedback",
                },
            )

        # Recuperer le PV et son imprimante
        # / Get the POS and its printer
        try:
            point_de_vente = PointDeVente.objects.select_related("printer").get(
                uuid=uuid_pv
            )
        except (PointDeVente.DoesNotExist, ValueError):
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Point de vente introuvable"),
                    "selector_bt_retour": "#print-feedback",
                },
            )

        if not point_de_vente.printer or not point_de_vente.printer.active:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _(
                        "Aucune imprimante configuree pour ce point de vente"
                    ),
                    "selector_bt_retour": "#print-feedback",
                },
            )

        # Recuperer les lignes de cette transaction
        # / Get the lines for this transaction
        lignes_du_paiement = LigneArticle.objects.filter(
            uuid_transaction=uuid_transaction_str,
        ).select_related("pricesold__productsold")

        if not lignes_du_paiement.exists():
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Aucune ligne trouvee pour cette transaction"),
                    "selector_bt_retour": "#print-feedback",
                },
            )

        # Construire le ticket et lancer l'impression async
        # / Build the ticket and launch async printing
        from laboutik.printing.formatters import formatter_ticket_vente
        from laboutik.printing.tasks import imprimer_async

        # Operateur = user connecte (admin session)
        # / Operator = logged-in user (admin session)
        operateur = request.user if request.user.is_authenticated else None

        # Moyen de paiement = celui de la premiere ligne
        # / Payment method = from the first line
        premiere_ligne = lignes_du_paiement.first()
        moyen_paiement = premiere_ligne.payment_method if premiere_ligne else ""

        ticket_data = formatter_ticket_vente(
            lignes_du_paiement,
            point_de_vente,
            operateur,
            moyen_paiement,
        )

        # Ajouter les metadonnees d'impression pour la tracabilite (LNE exigence 9)
        # / Add print metadata for tracking (LNE requirement 9)
        ticket_data["impression_meta"] = {
            "uuid_transaction": uuid_transaction_str,
            "cloture_uuid": None,
            "type_justificatif": "VENTE",
            "operateur_pk": str(operateur.pk) if operateur else None,
            "format_emission": "P",
        }

        imprimer_async.delay(
            str(point_de_vente.printer.pk),
            ticket_data,
            connection.schema_name,
        )

        return render(request, "laboutik/partial/hx_print_confirmation.html")

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

        try:
            ligne = LigneArticle.objects.get(uuid=ligne_uuid)
        except (LigneArticle.DoesNotExist, ValueError):
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Ligne d'article introuvable"),
                },
                status=404,
            )

        # Liste des moyens corrigeables (ESP/CB/CHQ), sans le moyen actuel
        # / List of correctable methods (CASH/CC/CHECK), without the current one
        moyens_corrigeables = []
        if ligne.payment_method != PaymentMethod.CASH:
            moyens_corrigeables.append(
                {"code": PaymentMethod.CASH, "label": _("Especes")}
            )
        if ligne.payment_method != PaymentMethod.CC:
            moyens_corrigeables.append(
                {"code": PaymentMethod.CC, "label": _("Carte bancaire")}
            )
        if ligne.payment_method != PaymentMethod.CHEQUE:
            moyens_corrigeables.append(
                {"code": PaymentMethod.CHEQUE, "label": _("Cheque")}
            )

        # Label humain du moyen actuel + montant en euros pour l'affichage
        # / Human label of current method + amount in euros for display
        moyen_actuel_label = LABELS_MOYENS_PAIEMENT_DB.get(
            ligne.payment_method, ligne.payment_method
        )
        montant_euros = f"{(ligne.amount or 0) / 100:.2f}"

        # Nom de l'article pour le contexte
        # / Article name for context
        nom_article = ""
        if ligne.pricesold and ligne.pricesold.productsold:
            nom_article = ligne.pricesold.productsold.product.name

        context = {
            "ligne": ligne,
            "moyens_corrigeables": moyens_corrigeables,
            "moyen_actuel_label": moyen_actuel_label,
            "montant_euros": montant_euros,
            "nom_article": nom_article,
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

        Gardes de securite / Security guards :
        1. Validation serializer (UUID valide, moyen dans ESP/CB/CHQ)
        2. NFC interdit (ancien moyen) — les paiements cashless sont lies a des Transactions fedow_core
        3. Post-cloture interdit — les lignes couvertes par une cloture sont immuables
        4. Meme moyen interdit — pas de correction sans changement
        """
        # --- Validation des champs via serializer DRF ---
        # Le serializer valide le format UUID, les choix de moyen, et la raison.
        # Les gardes metier (NFC, post-cloture, meme moyen) restent dans la vue
        # car elles dependent de l'etat en base.
        # / Field validation via DRF serializer.
        # Business guards (NFC, post-closure, same method) remain in the view
        # because they depend on database state.
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

        # --- Recuperer la ligne d'article ---
        # / Get the article line
        try:
            ligne = LigneArticle.objects.get(uuid=ligne_uuid)
        except LigneArticle.DoesNotExist:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Ligne d'article introuvable"),
                },
                status=404,
            )

        # --- GARDE 1 : les paiements NFC (cashless) ne peuvent pas etre corriges ---
        # Les paiements cashless sont lies a des Transactions fedow_core.
        # Modifier le moyen de paiement casserait la coherence avec le registre fedow.
        # / NFC payments are linked to fedow_core Transactions.
        # Changing the method would break coherence with the fedow ledger.
        moyens_nfc = (PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT)
        if ligne.payment_method in moyens_nfc:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _(
                        "Les paiements cashless ne peuvent pas etre modifies"
                    ),
                },
                status=400,
            )

        # --- GARDE 2 : post-cloture interdit ---
        # Les lignes couvertes par une cloture journaliere sont immuables.
        # / Lines covered by a daily closure are immutable.
        cloture_existante = ligne_couverte_par_cloture(ligne)
        if cloture_existante:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _(
                        "Cette vente est couverte par une cloture. Modification interdite."
                    ),
                },
                status=400,
            )

        # --- GARDE 3 : meme moyen = pas de correction ---
        # / Same method = no correction needed
        if ligne.payment_method == nouveau_moyen:
            return render(
                request,
                "laboutik/partial/hx_messages.html",
                {
                    "msg_type": "warning",
                    "msg_content": _("Le moyen de paiement est deja identique"),
                },
                status=400,
            )

        # --- Recuperer TOUTES les lignes de la transaction ---
        # Une transaction peut contenir plusieurs articles (ex: Biere + Coca).
        # La correction s'applique a toutes les lignes du meme paiement.
        # / Get ALL lines of the transaction.
        # A transaction may contain multiple articles (e.g. Beer + Soda).
        # The correction applies to all lines of the same payment.
        ancien_moyen = ligne.payment_method
        if ligne.uuid_transaction:
            lignes_transaction = LigneArticle.objects.filter(
                uuid_transaction=ligne.uuid_transaction,
                payment_method=ancien_moyen,
            )
        else:
            # Anciennes donnees sans uuid_transaction — corriger cette ligne seule
            # / Old data without uuid_transaction — correct this line only
            lignes_transaction = LigneArticle.objects.filter(uuid=ligne.uuid)

        # --- Creer les traces d'audit + modifier le moyen (atomique) ---
        # Les operations DOIVENT etre dans la meme transaction DB.
        # Une CorrectionPaiement est creee par LigneArticle pour la tracabilite.
        # / Create audit trails + modify the method (atomic).
        # One CorrectionPaiement per LigneArticle for traceability.
        operateur = request.user if request.user.is_authenticated else None
        nombre_lignes_corrigees = 0

        with db_transaction.atomic():
            for ligne_a_corriger in lignes_transaction:
                CorrectionPaiement.objects.create(
                    ligne_article=ligne_a_corriger,
                    ancien_moyen=ancien_moyen,
                    nouveau_moyen=nouveau_moyen,
                    raison=raison,
                    operateur=operateur,
                )
                # Note : le HMAC chain est casse volontairement. C'est attendu.
                # verifier_chaine() dans integrity.py croise avec CorrectionPaiement
                # pour distinguer correction tracee de falsification.
                # / Note: HMAC chain is intentionally broken. This is expected.
                ligne_a_corriger.payment_method = nouveau_moyen
                ligne_a_corriger.save(update_fields=["payment_method"])
                nombre_lignes_corrigees += 1

        logger.info(
            f"Correction paiement : {nombre_lignes_corrigees} ligne(s) "
            f"{ancien_moyen} → {nouveau_moyen} "
            f"par {request.user} — raison : {raison}"
        )

        # Re-rendre le detail complet de la vente avec le nouveau moyen
        # pour que la ligne se mette a jour visuellement.
        # / Re-render the full sale detail with the new method
        # so the row updates visually.
        ancien_moyen_label = LABELS_MOYENS_PAIEMENT_DB.get(ancien_moyen, ancien_moyen)
        nouveau_moyen_label = LABELS_MOYENS_PAIEMENT_DB.get(
            nouveau_moyen, nouveau_moyen
        )

        return render(
            request,
            "laboutik/partial/hx_correction_succes.html",
            {
                "ancien_moyen_label": ancien_moyen_label,
                "nouveau_moyen_label": nouveau_moyen_label,
                "ligne_uuid": str(ligne.uuid),
                "uuid_transaction": str(ligne.uuid_transaction)
                if ligne.uuid_transaction
                else str(ligne.uuid),
            },
        )


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

        state = _construire_state(point_de_vente)

        donnees_paiement = request.POST.dict()
        donnees_paiement["total"] = total_centimes
        somme_donnee_brute = donnees_paiement.get("given_sum", "")
        if somme_donnee_brute == "":
            donnees_paiement["given_sum"] = 0
        else:
            donnees_paiement["given_sum"] = int(somme_donnee_brute)
        donnees_paiement["missing"] = 0

        moyen_paiement_code = donnees_paiement.get("moyen_paiement", "")
        logger.info(
            f"payer_commande: commande={commande_uuid}, moyen={moyen_paiement_code}, "
            f"total={total_centimes}cts, articles={len(articles_panier)}"
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

                # NFC réussi → mettre à jour commande + table
                # NFC succeeded → update order + table
                commande.statut = CommandeSauvegarde.PAID
                commande.save(update_fields=["statut"])

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
            _creer_lignes_articles(
                articles_panier,
                moyen_paiement_code,
                point_de_vente=point_de_vente,
            )

            # Marquer la commande comme payée
            # Mark order as paid
            commande.statut = CommandeSauvegarde.PAID
            commande.save(update_fields=["statut"])

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

        # Broadcast WebSocket pour synchroniser les autres caisses
        # / WebSocket broadcast to sync other POS terminals
        donnees_broadcast = [
            {
                "product_uuid": str(product.uuid),
                "quantite": stock.quantite,
                "unite": stock.unite,
                "en_alerte": stock.est_en_alerte(),
                "en_rupture": stock.est_en_rupture(),
                "bloquant": stock.est_en_rupture()
                and not stock.autoriser_vente_hors_stock,
                "quantite_lisible": _formater_stock_lisible(
                    stock.quantite, stock.unite
                ),
            }
        ]
        broadcast_stock_update(donnees_broadcast)

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
        donnees_broadcast = [
            {
                "product_uuid": str(product.uuid),
                "quantite": stock.quantite,
                "unite": stock.unite,
                "en_alerte": stock.est_en_alerte(),
                "en_rupture": stock.est_en_rupture(),
                "bloquant": stock.est_en_rupture()
                and not stock.autoriser_vente_hors_stock,
                "quantite_lisible": _formater_stock_lisible(
                    stock.quantite, stock.unite
                ),
            }
        ]
        broadcast_stock_update(donnees_broadcast)

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
    rate = '10/min'
    scope = 'laboutik_auth_bridge'


@method_decorator(csrf_exempt, name='dispatch')
class LaBoutikAuthBridgeView(APIView):
    """
    Pont d'authentification hardware : échange une clé API contre un cookie session.
    / Hardware auth bridge: trades an API key for a session cookie.

    LOCALISATION : laboutik/views.py

    Flux :
    1. Client POST avec header Authorization: Api-Key xxx
    2. Validation de la clé (401 si invalide)
    3. Si la clé n'a pas de user lié (legacy V1) : 400
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
    Reçoit : Header Authorization: Api-Key <key>
    Émet : 204 No Content + Set-Cookie: sessionid=<key>
    Erreurs : 401 si clé absente/invalide/révoquée, 400 si clé V1, 429 si throttle
    """
    permission_classes = [AllowAny]
    throttle_classes = [BridgeThrottle]

    def post(self, request):
        # Extraction de la clé depuis le header Authorization
        # / Extract key from Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Api-Key '):
            # Log : tentative d'accès sans header Api-Key
            # / Log: access attempt without Api-Key header
            logger.warning(
                "laboutik bridge: missing/malformed Authorization header from %s",
                request.META.get('REMOTE_ADDR'),
            )
            return HttpResponse(status=401)

        api_key_string = auth_header[len('Api-Key '):].strip()
        if not api_key_string:
            logger.warning(
                "laboutik bridge: empty API key from %s",
                request.META.get('REMOTE_ADDR'),
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
                request.META.get('REMOTE_ADDR'),
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
                _("Legacy API key, bridge flow not available. Please re-pair the device."),
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
        return HttpResponse(status=204)
