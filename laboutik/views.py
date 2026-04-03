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
from json import dumps

from django.conf import settings
from django.db import transaction as db_transaction
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django_htmx.http import HttpResponseClientRedirect
from rest_framework import viewsets
from rest_framework.decorators import action

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import F, Max, Prefetch, Sum, Count, Q
from django.db.models.functions import Coalesce

from fedow_core.exceptions import SoldeInsuffisant
from fedow_core.models import Asset
from fedow_core.services import TransactionService, WalletService

from AuthBillet.models import Wallet
from AuthBillet.utils import get_or_create_user
from django.utils import timezone as dj_timezone

from BaseBillet.models import (
    Configuration, Event, LigneArticle, Membership, Price, PriceSold, Product,
    ProductSold, SaleOrigin, PaymentMethod, Ticket,
)
from BaseBillet.permissions import HasLaBoutikAccess
from QrcodeCashless.models import CarteCashless
from laboutik.models import (
    LaboutikConfiguration,
    PointDeVente, CartePrimaire, Table,
    CommandeSauvegarde, ArticleCommandeSauvegarde,
    ClotureCaisse, CorrectionPaiement, SortieCaisse,
    HistoriqueFondDeCaisse,
)
from laboutik.serializers import (
    ClientIdentificationSerializer,
    CartePrimaireSerializer, PanierSerializer,
    CommandeSerializer, ArticleCommandeSerializer,
    ClotureSerializer, EnvoyerRapportSerializer,
)
from laboutik.reports import RapportComptableService
from laboutik.utils import method as payment_method
from laboutik.integrity import (
    calculer_hmac, obtenir_previous_hmac, calculer_total_ht, ligne_couverte_par_cloture,
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
        chemin_version = settings.BASE_DIR / 'VERSION'
        with open(chemin_version, 'r') as fichier:
            for ligne in fichier:
                ligne = ligne.strip()
                if ligne.startswith('VERSION='):
                    return ligne.split('=', 1)[1]
    except FileNotFoundError:
        pass
    return '?'


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


def _construire_donnees_articles(point_de_vente_instance):
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
        'prices',
        queryset=Price.objects.filter(publish=True, asset__isnull=True).order_by('order'),
        to_attr='prix_euros',
    )

    # Produits du M2M du PV : articles POS (methode_caisse) OU adhesions (categorie_article)
    # Les adhesions n'ont pas forcement de methode_caisse, elles sont identifiees par categorie_article.
    # / POS M2M products: POS articles (methode_caisse) OR memberships (categorie_article)
    # Memberships don't necessarily have methode_caisse, identified by categorie_article.
    produits = list(
        point_de_vente_instance.products
        .filter(Q(methode_caisse__isnull=False) | Q(categorie_article=Product.ADHESION))
        .select_related('categorie_pos')
        .prefetch_related(prix_euros_prefetch)
        .order_by('poids', 'name')
    )

    now = dj_timezone.now()
    articles = []
    for product in produits:
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
        multi_tarif = len(product.prix_euros) > 1 or a_prix_libre

        tarifs = []
        if multi_tarif:
            for p in product.prix_euros:
                tarifs.append({
                    "price_uuid": str(p.uuid),
                    "name": p.name,
                    "prix_centimes": int(round(p.prix * 100)),
                    "free_price": p.free_price,
                    "subscription_label": p.get_subscription_type_display() if hasattr(p, 'get_subscription_type_display') else "",
                })

        # Couleurs : override produit si défini, sinon catégorie
        # Colors: product override if set, otherwise category
        couleur_backgr = product.couleur_fond_pos or (categorie_pos.couleur_fond if categorie_pos else "#17a2b8")
        couleur_texte_article = product.couleur_texte_pos or (categorie_pos.couleur_texte if categorie_pos else "#333333")

        # Icône : override produit si défini, sinon icône de la catégorie, sinon rien
        # Icon: product override if set, otherwise category icon, otherwise nothing
        icone_brute = product.icon_pos or (categorie_pos.icon if categorie_pos else None) or ""

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
            "tarifs": tarifs,
            "tarifs_json": dumps(tarifs) if tarifs else "[]",
            "methode_caisse": product.methode_caisse or "",
            # RC (cadeau) et TM (temps) : pas de symbole € sur le prix,
            # car ce ne sont pas des euros mais des unites de monnaie cadeau/temps.
            # / RC (gift) and TM (time): no € symbol on the price,
            # because they are not euros but gift/time currency units.
            "est_recharge_gratuite": product.methode_caisse in METHODES_RECHARGE_GRATUITES,
        }

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
    if est_pv_billetterie:
        from BaseBillet.models import Ticket  # Import ici pour eviter circulaire / Import here to avoid circular

        events_futurs = (
            Event.objects
            .filter(
                published=True,
                archived=False,
                datetime__gte=now - timedelta(days=1),
            )
            .prefetch_related('products__prices')
            .order_by('datetime')
        )

        # Palette de couleurs pour distinguer les events visuellement
        # Chaque event reçoit une couleur de fond unique.
        # / Color palette to visually distinguish events.
        # Each event gets a unique background color.
        couleurs_events = [
            '#7C3AED',  # violet
            '#2563EB',  # bleu
            '#059669',  # vert emeraude
            '#D97706',  # ambre
            '#DC2626',  # rouge
            '#7C3AED',  # violet (cycle)
            '#0891B2',  # cyan
            '#BE185D',  # rose
        ]

        for index_event, event in enumerate(events_futurs):
            places_vendues_event = event.valid_tickets_count()
            jauge_max_event = event.jauge_max or 0
            est_complet_event = event.complet()
            pourcentage_event = (
                int(round(places_vendues_event / jauge_max_event * 100))
                if jauge_max_event else 0
            )

            # Couleur de fond par event (palette cyclique)
            # / Background color per event (cyclic palette)
            couleur_fond_event = couleurs_events[index_event % len(couleurs_events)]

            # Produits publiés de cet event avec au moins un prix EUR
            # / Published products of this event with at least one EUR price
            produits_event = event.products.filter(publish=True)
            if not produits_event.exists():
                continue

            for product in produits_event:
                # Couleurs : couleur event par défaut, override par le produit si défini
                # / Colors: event color by default, product override if set
                categorie_pos = product.categorie_pos
                couleur_fond = product.couleur_fond_pos or couleur_fond_event
                couleur_texte = (
                    product.couleur_texte_pos
                    or (categorie_pos.couleur_texte if categorie_pos else None)
                    or '#ffffff'
                )
                icone_brute = (
                    product.icon_pos
                    or (categorie_pos.icon if categorie_pos else None)
                    or 'fa-ticket-alt'
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

                # Pour chaque Price publiée en EUR (asset=null) → 1 tuile
                # / For each published EUR Price (asset=null) → 1 tile
                prix_euros = product.prices.filter(
                    publish=True, asset__isnull=True
                ).order_by('order')

                for price in prix_euros:
                    prix_en_centimes = int(round(price.prix * 100))

                    # Jauge : Price.stock si défini, sinon Event.jauge_max
                    # / Gauge: Price.stock if set, otherwise Event.jauge_max
                    if price.stock is not None and price.stock > 0:
                        # Jauge par tarif — compter les tickets vendus pour cette Price
                        # / Per-rate gauge — count tickets sold for this Price
                        places_vendues_price = Ticket.objects.filter(
                            reservation__event__pk=event.pk,
                            pricesold__price__pk=price.pk,
                            status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED],
                        ).count()
                        jauge_max_tuile = price.stock
                        places_vendues_tuile = places_vendues_price
                        est_complet_tuile = price.out_of_stock(event)
                    else:
                        # Jauge globale de l'event
                        # / Global event gauge
                        jauge_max_tuile = jauge_max_event
                        places_vendues_tuile = places_vendues_event
                        est_complet_tuile = est_complet_event

                    pourcentage_tuile = (
                        int(round(places_vendues_tuile / jauge_max_tuile * 100))
                        if jauge_max_tuile else 0
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
                            "places_restantes": max(0, jauge_max_tuile - places_vendues_tuile) if jauge_max_tuile else None,
                            "pourcentage": pourcentage_tuile,
                            "complet": est_complet_tuile,
                        },
                    }
                    articles.append(article_billet)

    return articles


def _construire_donnees_categories(point_de_vente_instance):
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
    categories_qs = point_de_vente_instance.categories.order_by('poid_liste', 'name')
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
        categories.append({
            "id": str(categorie.uuid),
            "name": categorie.name,
            "icon": icone_cat,
            "icone_type": icone_type_cat,
        })

    # PV BILLETTERIE : ajouter les events futurs comme pseudo-catégories
    # La jauge event dans la sidebar = jauge globale (toutes catégories confondues)
    # / BILLETTERIE POS: add future events as pseudo-categories
    # Event gauge in sidebar = global gauge (all rates combined)
    est_pv_billetterie = (
        point_de_vente_instance.comportement == PointDeVente.BILLETTERIE
    )
    if est_pv_billetterie:
        now = dj_timezone.now()
        events_futurs = Event.objects.filter(
            published=True,
            archived=False,
            datetime__gte=now - timedelta(days=1),
        ).order_by('datetime')

        for event in events_futurs:
            # Ignorer les events sans produit publié
            # / Skip events without published products
            if not event.products.filter(publish=True).exists():
                continue

            places_vendues = event.valid_tickets_count()
            jauge_max = event.jauge_max or 0
            pourcentage = (
                int(round(places_vendues / jauge_max * 100))
                if jauge_max else 0
            )
            categories.append({
                "id": str(event.uuid),
                "name": event.name,
                "icon": "fa-calendar-alt",
                "icone_type": "fa",
                "is_event": True,
                "date": event.datetime,
                "jauge_max": jauge_max,
                "places_vendues": places_vendues,
                "pourcentage": pourcentage,
                "complet": event.complet(),
            })

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
    carte.save(update_fields=['wallet_ephemere'])
    logger.info(f"Wallet éphémère créé pour carte {carte.tag_id}: {wallet.uuid}")
    return wallet


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
METHODES_RECHARGE = (Product.RECHARGE_EUROS, Product.RECHARGE_CADEAU, Product.RECHARGE_TEMPS)

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
        if article['product'].methode_caisse in METHODES_RECHARGE:
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
        if article['product'].methode_caisse in METHODES_RECHARGE_PAYANTES:
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
        if article['product'].methode_caisse not in METHODES_RECHARGE_GRATUITES:
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
    permission_classes = [HasLaBoutikAccess]

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

    @action(detail=False, methods=["post"], url_path="carte_primaire", url_name="carte_primaire")
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
            return render(request, "laboutik/partial/hx_primary_card_message.html", {
                "msg": str(premiere_erreur),
            })

        tag_id_carte_manager = serializer.validated_data["tag_id"]
        logger.debug(f"carte_primaire: tag_id reçu = {tag_id_carte_manager}")

        # Chercher la carte primaire depuis le tag NFC
        # Look up the primary card from the NFC tag
        carte_primaire_obj, erreur = _charger_carte_primaire(tag_id_carte_manager)
        if erreur is not None:
            logger.debug(f"carte_primaire: {erreur}")
            return render(request, "laboutik/partial/hx_primary_card_message.html", {
                "msg": erreur,
            })

        # Points de vente accessibles (non masqués) — évalué une seule fois
        # Accessible points of sale (not hidden) — evaluated once
        pvs = list(
            carte_primaire_obj.points_de_vente.filter(hidden=False).order_by('poid_liste')
        )
        nombre_de_pvs = len(pvs)

        if nombre_de_pvs == 0:
            logger.debug("carte_primaire: Aucun PV configuré")
            return render(request, "laboutik/partial/hx_primary_card_message.html", {
                "msg": _("Aucun point de vente configuré"),
            })

        # Toujours rediriger vers le premier PV de la liste (tri par poid_liste).
        # Comportement original de LaBoutik : pas de page de choix intermediaire.
        # Always redirect to the first POS in the list (sorted by poid_liste).
        pv = pvs[0]
        url_point_de_vente = reverse("laboutik-caisse-point_de_vente")
        url_avec_params = f"{url_point_de_vente}?uuid_pv={pv.uuid}&tag_id_cm={tag_id_carte_manager}"
        logger.debug(f"carte_primaire: Redirection vers {url_avec_params}")
        return HttpResponseClientRedirect(url_avec_params)

    @action(detail=False, methods=["get"], url_path="point_de_vente", url_name="point_de_vente")
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
                    carte_primaire_obj.points_de_vente
                    .filter(hidden=False)
                    .order_by('poid_liste')
                    .values_list('uuid', 'name', 'poid_liste', 'icon')
                )

        # --- Construire les données articles et catégories ---
        # --- Build article and category data ---
        articles = _construire_donnees_articles(pv)
        categories = _construire_donnees_categories(pv)

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
            ) if carte_primaire_obj else "",
            "mode_gerant": carte_primaire_obj.edit_mode if carte_primaire_obj else False,
            "pvs_list": [
                {"uuid": str(uuid), "name": name, "poid_liste": poid, "icon": icon or ""}
                for uuid, name, poid, icon in pvs_list
            ],
        }

        # --- Tables (mode restaurant) ---
        # --- Tables (restaurant mode) ---
        tables_list = []
        if pv.accepte_commandes:
            tables_qs = Table.objects.filter(archive=False).order_by('poids', 'name')
            for table in tables_qs:
                tables_list.append({
                    "id": str(table.uuid),
                    "name": table.name,
                    "statut": table.statut,
                })

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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=404)

        # --- 4. Calculer datetime_ouverture automatiquement ---
        # Trouver la derniere cloture journaliere de ce PV
        # / Find the last daily closure for this PV
        derniere_cloture = ClotureCaisse.objects.filter(
            point_de_vente=point_de_vente,
            niveau=ClotureCaisse.JOURNALIERE,
        ).order_by('-datetime_cloture').first()

        if derniere_cloture:
            # datetime_ouverture = 1ere LigneArticle VALID apres la derniere cloture
            # / datetime_ouverture = 1st VALID LigneArticle after the last closure
            premiere_vente = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
                status=LigneArticle.VALID,
                datetime__gt=derniere_cloture.datetime_cloture,
            ).order_by('datetime').first()
        else:
            # Aucune cloture precedente : 1ere LigneArticle VALID tous temps confondus
            # / No previous closure: 1st VALID LigneArticle ever
            premiere_vente = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
                status=LigneArticle.VALID,
            ).order_by('datetime').first()

        if not premiere_vente:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Aucune vente à clôturer"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

        datetime_ouverture = premiere_vente.datetime

        # --- 5. Calculer le rapport via RapportComptableService ---
        # --- 5. Compute the report via RapportComptableService ---
        datetime_cloture = dj_timezone.now()
        service = RapportComptableService(point_de_vente, datetime_ouverture, datetime_cloture)
        rapport = service.generer_rapport_complet()
        totaux = rapport['totaux_par_moyen']
        hash_lignes = service.calculer_hash_lignes()

        # Extraire les totaux pour la ClotureCaisse et l'affichage
        # / Extract totals for ClotureCaisse and display
        total_especes = totaux['especes']
        total_carte_bancaire = totaux['carte_bancaire']
        total_cashless = totaux['cashless']
        total_general = totaux['total']
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
            clotures_niveau = ClotureCaisse.objects.select_for_update().filter(
                niveau=ClotureCaisse.JOURNALIERE,
            ).order_by('-numero_sequentiel')

            dernier_seq = clotures_niveau.first()
            numero_sequentiel = (dernier_seq.numero_sequentiel + 1) if dernier_seq else 1

            # Total perpetuel : mise a jour atomique avec F() puis refresh
            # / Perpetual total: atomic update with F() then refresh
            config = LaboutikConfiguration.get_solo()
            LaboutikConfiguration.objects.filter(pk=config.pk).update(
                total_perpetuel=F('total_perpetuel') + total_general
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
        for taux_label, tva_data in rapport['tva'].items():
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

    @action(detail=True, methods=["get"], url_path="rapport_pdf", url_name="rapport_pdf")
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
                'point_de_vente', 'responsable',
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

    @action(detail=True, methods=["get"], url_path="rapport_csv", url_name="rapport_csv")
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
                'point_de_vente', 'responsable',
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

    @action(detail=True, methods=["post"], url_path="envoyer_rapport", url_name="envoyer_rapport")
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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

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

    @action(detail=False, methods=["post"], url_path="imprimer-ticket-x", url_name="imprimer_ticket_x")
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
            point_de_vente = PointDeVente.objects.select_related('printer').get(uuid=uuid_pv)
        except (PointDeVente.DoesNotExist, ValueError):
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Point de vente introuvable"),
            }, status=404)

        if not point_de_vente.printer or not point_de_vente.printer.active:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Aucune imprimante configuree pour ce point de vente"),
            }, status=400)

        # Calculer le rapport du service en cours / Compute current shift report
        datetime_ouverture = _calculer_datetime_ouverture_service()
        if datetime_ouverture is None:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Aucune vente en cours — rien a imprimer"),
            }, status=400)

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

        return render(request, "laboutik/partial/hx_messages.html", {
            "msg_type": "success",
            "msg_content": _("Ticket X envoye a l'imprimante"),
        })

    # ----------------------------------------------------------------------- #
    #  Export fiscal — archive ZIP signee HMAC pour l'administration fiscale   #
    #  Fiscal export — HMAC-signed ZIP archive for tax administration          #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["get", "post"], url_path="export-fiscal", url_name="export_fiscal")
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
            est_requete_htmx = request.headers.get('HX-Request') == 'true'
            if est_requete_htmx:
                return render(request, "admin/cloture/export_fiscal_form.html", {
                    "form_action_url": request.path,
                    "cancel_url": request.headers.get('HX-Current-URL', '/admin/laboutik/cloturecaisse/'),
                })
            return render(request, "laboutik/partial/hx_export_fiscal.html")

        # --- POST : generation de l'archive ZIP ---
        # --- POST: ZIP archive generation ---

        # Recuperer la cle HMAC / Get the HMAC key
        cle = config.get_or_create_hmac_key()
        if not cle:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Cle HMAC non configuree. Export impossible."),
            }, status=500)

        # Parser les dates optionnelles / Parse optional dates
        debut = None
        fin = None
        debut_str = request.POST.get('debut', '').strip()
        fin_str = request.POST.get('fin', '').strip()
        try:
            if debut_str:
                debut = date_type.fromisoformat(debut_str)
            if fin_str:
                fin = date_type.fromisoformat(fin_str)
        except ValueError:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Format de date invalide."),
            }, status=400)

        schema = connection.schema_name

        # Generer les fichiers, calculer les hash, empaqueter en ZIP
        # / Generate files, compute hashes, package into ZIP
        fichiers = generer_fichiers_archive(schema, debut, fin)
        hash_json = calculer_hash_fichiers(fichiers, cle)
        zip_bytes = empaqueter_zip(fichiers, hash_json)

        # Journaliser l'export / Log the export
        details = {
            'schema': schema,
            'debut': debut_str or None,
            'fin': fin_str or None,
            'nb_fichiers': len(fichiers),
            'taille_zip': len(zip_bytes),
        }
        creer_entree_journal(
            type_operation='EXPORT_FISCAL',
            details=details,
            cle_secrete=cle,
            operateur=request.user if request.user.is_authenticated else None,
        )

        # Reponse ZIP en telechargement / ZIP download response
        date_label = dj_timezone.localtime(dj_timezone.now()).strftime('%Y%m%d_%H%M')
        filename = f"export_fiscal_{schema}_{date_label}.zip"
        response = HttpResponse(zip_bytes, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    # ----------------------------------------------------------------------- #
    #  Export FEC — fichier des ecritures comptables (18 colonnes)              #
    #  FEC export — accounting entries file (18 columns)                        #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["get", "post"], url_path="export-fec", url_name="export_fec")
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
            est_requete_htmx = request.headers.get('HX-Request') == 'true'
            if est_requete_htmx:
                return render(request, "admin/cloture/export_fec_form.html", {
                    "form_action_url": request.path,
                    "cancel_url": request.headers.get('HX-Current-URL', '/admin/laboutik/cloturecaisse/'),
                })
            return render(request, "laboutik/partial/hx_export_fiscal.html")

        # --- POST : generation du fichier FEC ---
        # --- POST: FEC file generation ---

        # Parser les dates optionnelles / Parse optional dates
        debut = None
        fin = None
        debut_str = request.POST.get('debut', '').strip()
        fin_str = request.POST.get('fin', '').strip()
        try:
            if debut_str:
                debut = date_type.fromisoformat(debut_str)
            if fin_str:
                fin = date_type.fromisoformat(fin_str)
        except ValueError:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Format de date invalide."),
            }, status=400)

        # Filtrer les clotures journalieres / Filter daily closures
        clotures = ClotureCaisse.objects.filter(niveau=ClotureCaisse.JOURNALIERE).order_by('datetime_cloture')
        if debut:
            clotures = clotures.filter(datetime_cloture__date__gte=debut)
        if fin:
            clotures = clotures.filter(datetime_cloture__date__lte=fin)

        if not clotures.exists():
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Aucune cloture journaliere trouvee pour la periode."),
            }, status=404)

        schema = connection.schema_name
        contenu_fec, nom_fichier, avertissements = generer_fec(clotures, schema)

        response = HttpResponse(contenu_fec, content_type='text/tab-separated-values; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
        return response

    # ----------------------------------------------------------------------- #
    #  Export CSV comptable — multi-profils (Sage, EBP, Dolibarr, etc.)       #
    #  CSV accounting export — multi-profile (Sage, EBP, Dolibarr, etc.)      #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["get", "post"], url_path="export-csv-comptable", url_name="export_csv_comptable")
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
            return render(request, "admin/cloture/export_csv_comptable_form.html", {
                "form_action_url": request.path,
                "profils": PROFILS,
            })

        # --- POST : generation du fichier CSV comptable ---
        # --- POST: accounting CSV file generation ---

        # Valider le profil choisi / Validate the chosen profile
        profil_nom = request.POST.get('profil', '').strip()
        if profil_nom not in PROFILS:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Profil inconnu. Choix : %(profils)s") % {
                    "profils": ", ".join(PROFILS.keys()),
                },
            }, status=400)

        # Parser les dates optionnelles / Parse optional dates
        debut = None
        fin = None
        debut_str = request.POST.get('debut', '').strip()
        fin_str = request.POST.get('fin', '').strip()
        try:
            if debut_str:
                debut = date_type.fromisoformat(debut_str)
            if fin_str:
                fin = date_type.fromisoformat(fin_str)
        except ValueError:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Format de date invalide."),
            }, status=400)

        # Filtrer les clotures journalieres / Filter daily closures
        clotures = ClotureCaisse.objects.filter(niveau=ClotureCaisse.JOURNALIERE).order_by('datetime_cloture')
        if debut:
            clotures = clotures.filter(datetime_cloture__date__gte=debut)
        if fin:
            clotures = clotures.filter(datetime_cloture__date__lte=fin)

        if not clotures.exists():
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Aucune cloture journaliere trouvee pour la periode."),
            }, status=404)

        schema = connection.schema_name
        contenu_bytes, nom_fichier, avertissements = generer_csv_comptable(clotures, profil_nom, schema)

        profil = PROFILS[profil_nom]
        content_type = 'text/csv; charset=' + profil["encodage"]
        response = HttpResponse(contenu_bytes, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{nom_fichier}"'
        return response

    # ----------------------------------------------------------------------- #
    #  Charger plan comptable — jeu de comptes par defaut                      #
    #  Load chart of accounts — default account set                            #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["post"], url_path="charger-plan-comptable", url_name="charger_plan_comptable")
    def charger_plan_comptable(self, request):
        """
        POST /laboutik/caisse/charger-plan-comptable/
        Charge un jeu de comptes comptables par defaut (bar_resto ou association).
        / Loads a default chart of accounts set (bar_resto or association).

        LOCALISATION : laboutik/views.py
        """
        from django.core.management import call_command
        from django.db import connection

        jeu = request.POST.get('jeu', '').strip()
        if jeu not in ('bar_resto', 'association'):
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Jeu de comptes invalide."),
            }, status=400)

        # Verifier si des comptes existent deja — si oui, forcer le reset
        # Sinon la commande afficherait un warning et ne ferait rien
        # / Check if accounts already exist — if so, force reset
        from laboutik.models import CompteComptable
        nb_existants = CompteComptable.objects.count()

        try:
            call_command(
                'charger_plan_comptable',
                schema=connection.schema_name,
                jeu=jeu,
                reset=nb_existants > 0,
            )
        except Exception as e:
            logger.error(f"Erreur chargement plan comptable : {e}")
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": str(e),
            }, status=500)

        message = _("Plan comptable charge avec succes.")
        if nb_existants > 0:
            message = _("Plan comptable remplace avec succes (%(nb)s comptes precedents supprimes).") % {
                "nb": nb_existants,
            }

        return render(request, "laboutik/partial/hx_messages.html", {
            "msg_type": "success",
            "msg_content": message,
        })

    # ----------------------------------------------------------------------- #
    #  Fond de caisse — lecture et modification du montant initial              #
    #  Cash float — read and update initial drawer amount                      #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["get", "post"], url_path="fond-de-caisse", url_name="fond_de_caisse")
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
                return render(request, "laboutik/partial/hx_messages.html", {
                    "msg_type": "warning",
                    "msg_content": str(premiere_erreur),
                }, status=400)

            montant_centimes = serializer.validated_data['montant_euros']

            # Trace du changement de fond de caisse avant modification
            # / Record cash float change before modification
            uuid_pv = request.POST.get('uuid_pv') or request.GET.get('uuid_pv')
            point_de_vente_pour_historique = None
            if uuid_pv:
                point_de_vente_pour_historique = PointDeVente.objects.filter(uuid=uuid_pv).first()

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

    @action(detail=False, methods=["get"], url_path="sortie-de-caisse", url_name="sortie_de_caisse")
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
            "fond_de_caisse_euros": f"{fond_de_caisse_centimes / 100:.2f}".replace('.', ','),
            "entrees_especes_euros": f"{entrees_especes_centimes / 100:.2f}".replace('.', ','),
            "solde_total_euros": f"{solde_total_centimes / 100:.2f}".replace('.', ','),
        }
        return render(request, "laboutik/partial/hx_sortie_de_caisse.html", context)

    @action(detail=False, methods=["post"], url_path="creer-sortie-de-caisse", url_name="creer_sortie_de_caisse")
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
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": str(premiere_erreur),
            }, status=400)

        uuid_pv = serializer.validated_data['uuid_pv']
        note = serializer.validated_data.get('note', '').strip()

        # Recuperer le point de vente
        # / Get the point of sale
        try:
            point_de_vente = PointDeVente.objects.get(uuid=uuid_pv)
        except PointDeVente.DoesNotExist:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Point de vente introuvable"),
            }, status=404)

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
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Aucune coupure saisie"),
            }, status=400)

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
        return render(request, "laboutik/partial/hx_sortie_succes.html", {
            "montant_euros": montant_euros,
            "params_ventes": params_ventes,
        })

    # ----------------------------------------------------------------------- #
    #  Menu Ventes — Ticket X + liste des ventes (Session 16)                  #
    #  Sales menu — Ticket X + sales list (Session 16)                         #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["get"], url_path="recap-en-cours", url_name="recap_en_cours")
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
            return _rendre_vue_ventes(request, "laboutik/partial/hx_recap_en_cours.html", context)

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

        return _rendre_vue_ventes(request, "laboutik/partial/hx_recap_en_cours.html", context)

    @action(detail=False, methods=["get"], url_path="liste-ventes", url_name="liste_ventes")
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
            return _rendre_vue_ventes(request, "laboutik/partial/hx_liste_ventes.html", context)

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
        ventes_requete = lignes.values(
            cle_vente=Coalesce('uuid_transaction', 'uuid'),
        ).annotate(
            derniere_datetime=Max('datetime'),
            total=Sum('amount'),
            nb_articles=Count('uuid'),
            moyen_paiement=Max('payment_method'),
            nom_pv=Max('point_de_vente__name'),
        ).order_by('-derniere_datetime')

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
        ventes_page = list(ventes_requete[offset:offset + taille_page])
        a_page_suivante = ventes_requete[offset + taille_page:offset + taille_page + 1].exists()

        # Ajouter le label humain du moyen de paiement a chaque vente
        # (le queryset renvoie le code brut "CA", "CC", etc.)
        # / Add human-readable payment method label to each sale
        for vente in ventes_page:
            code_moyen = vente.get('moyen_paiement', '')
            vente['moyen_paiement_label'] = LABELS_MOYENS_PAIEMENT_DB.get(code_moyen, code_moyen)

        # Liste des PV pour le filtre (select)
        # / POS list for the filter (select)
        points_de_vente = PointDeVente.objects.filter(
            hidden=False,
        ).order_by('poid_liste').values('uuid', 'name')

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
        return _rendre_vue_ventes(request, "laboutik/partial/hx_liste_ventes.html", context)

    @action(
        detail=False, methods=["get"],
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
            return render(request, "laboutik/partial/hx_messages.html", context, status=404)

        # Recuperer les lignes de cette transaction.
        # La cle peut etre un uuid_transaction (regroupement) ou un uuid de ligne
        # (ventes sans uuid_transaction, anciennes donnees).
        # On cherche d'abord par uuid_transaction, puis par uuid (pk).
        # / Get all lines for this transaction.
        # The key can be a uuid_transaction (grouped) or a line uuid
        # (sales without uuid_transaction, old data).
        # Try uuid_transaction first, then uuid (pk).
        lignes = LigneArticle.objects.filter(
            uuid_transaction=uuid_tx_valide,
            sale_origin=SaleOrigin.LABOUTIK,
        ).select_related(
            'pricesold__productsold__product',
            'pricesold__price',
            'point_de_vente',
        ).order_by('datetime')

        # Si pas trouve par uuid_transaction, chercher par uuid (pk de la ligne)
        # / If not found by uuid_transaction, search by uuid (line pk)
        if not lignes.exists():
            lignes = LigneArticle.objects.filter(
                uuid=uuid_tx_valide,
                sale_origin=SaleOrigin.LABOUTIK,
            ).select_related(
                'pricesold__productsold__product',
                'pricesold__price',
                'point_de_vente',
            ).order_by('datetime')

        if not lignes.exists():
            context = {
                "msg_type": "warning",
                "msg_content": _("Transaction introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context, status=404)

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

            articles_detail.append({
                "nom": nom_article,
                "tarif": nom_tarif,
                "qty": ligne.qty,
                "montant": ligne.amount or 0,
            })
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
        moyen_paiement_label = LABELS_MOYENS_PAIEMENT_DB.get(moyen_de_la_ligne, moyen_de_la_ligne)

        context = {
            "uuid_transaction": uuid_transaction,
            "datetime": premiere_ligne.datetime,
            "moyen_paiement": moyen_de_la_ligne,
            "moyen_paiement_label": moyen_paiement_label,
            "nom_pv": premiere_ligne.point_de_vente.name if premiere_ligne.point_de_vente else "",
            "articles": articles_detail,
            "total": total_transaction,
            "nb_articles": len(articles_detail),
            "correction_possible": correction_est_possible,
            "premiere_ligne_uuid": str(premiere_ligne.uuid),
        }
        return _rendre_vue_ventes(request, "laboutik/partial/hx_detail_vente.html", context)


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
    derniere_cloture = ClotureCaisse.objects.filter(
        niveau=ClotureCaisse.JOURNALIERE,
    ).order_by('-datetime_cloture').first()

    if derniere_cloture:
        premiere_vente = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            status=LigneArticle.VALID,
            datetime__gt=derniere_cloture.datetime_cloture,
        ).order_by('datetime').first()
    else:
        premiere_vente = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            status=LigneArticle.VALID,
        ).order_by('datetime').first()

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
                carte_primaire_obj.points_de_vente
                .filter(hidden=False)
                .order_by('poid_liste')
                .values_list('uuid', 'name', 'poid_liste', 'icon')
            )
            card_dict["pvs_list"] = [
                {"uuid": str(uuid), "name": name, "poid_liste": poid, "icon": icon or ""}
                for uuid, name, poid, icon in pvs_list
            ]

    # URL de retour vers l'interface POS
    # / Return URL to the POS interface
    url_retour_pv = reverse('laboutik-caisse-point_de_vente')
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
        not hasattr(request, 'htmx')
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
    :return: liste de dicts {'product', 'price', 'quantite', 'prix_centimes', 'custom_amount_centimes'}
    """
    articles_extraits = PanierSerializer.extraire_articles_du_post(donnees_post)
    if not articles_extraits:
        return []

    # Charger tous les produits du PV en une seule requête (avec prix EUR préchargés)
    # Load all PV products in a single query (with EUR prices prefetched)
    prix_euros_prefetch = Prefetch(
        'prices',
        queryset=Price.objects.filter(publish=True, asset__isnull=True).order_by('order'),
        to_attr='prix_euros',
    )
    # Produits du PV : ceux avec methode_caisse (articles POS) OU categorie_article=ADHESION
    # Les adhesions n'ont pas forcement de methode_caisse (elles sont identifiees par categorie_article).
    # / POS products: those with methode_caisse (POS articles) OR categorie_article=ADHESION
    # Memberships don't necessarily have methode_caisse (identified by categorie_article).
    produits_du_pv = {
        str(p.uuid): p
        for p in point_de_vente.products
        .filter(Q(methode_caisse__isnull=False) | Q(categorie_article=Product.ADHESION))
        .prefetch_related(prix_euros_prefetch)
    }

    articles_panier = []
    for article_data in articles_extraits:
        uuid_str = article_data['uuid']
        quantite = article_data['quantite']
        price_uuid_str = article_data.get('price_uuid')
        custom_amount_centimes = article_data.get('custom_amount_centimes')

        # --- Articles BILLETTERIE : ID composite "{event_uuid}__{price_uuid}" ---
        # Le JS envoie repid-{event_uuid}__{price_uuid} pour les tuiles billet.
        # On sépare event UUID et price UUID, puis on charge le Product via la Price.
        # / BILLETTERIE articles: composite ID "{event_uuid}__{price_uuid}".
        # The JS sends repid-{event_uuid}__{price_uuid} for ticket tiles.
        # We split event UUID and price UUID, then load the Product via the Price.
        produit = None
        event_billet = None
        est_billet = False

        if '__' in uuid_str and point_de_vente.comportement == PointDeVente.BILLETTERIE:
            event_uuid_str, price_uuid_str_billet = uuid_str.split('__', 1)
            try:
                prix_billet = Price.objects.select_related('product').get(
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
                produit.prices.filter(publish=True, asset__isnull=True).order_by('order')
            )

        # --- Articles POS classiques : chercher par Product UUID ---
        # / Standard POS articles: look up by Product UUID
        if produit is None:
            produit = produits_du_pv.get(uuid_str)

        if produit is None:
            logger.warning(f"Produit {uuid_str} non trouvé dans le PV {point_de_vente.name}")
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

        # Valider le prix libre (custom_amount_centimes)
        # Sécurité : rejeter les montants invalides au lieu de corriger silencieusement.
        # Un montant sous le minimum venant du front est soit un bug soit une tentative de fraude.
        # Validate free price (custom_amount_centimes)
        # Security: reject invalid amounts instead of silently correcting.
        # An amount below minimum from the frontend is either a bug or a fraud attempt.
        if custom_amount_centimes is not None:
            if not prix_obj.free_price:
                logger.warning(f"Prix {prix_obj.name} n'est pas un prix libre")
                custom_amount_centimes = None
            else:
                prix_minimum_centimes = int(round(prix_obj.prix * 100))
                if custom_amount_centimes < prix_minimum_centimes:
                    raise ValueError(
                        _("Montant libre (%(montant)s€) inférieur au minimum (%(minimum)s€)") % {
                            'montant': f"{custom_amount_centimes / 100:.2f}",
                            'minimum': f"{prix_minimum_centimes / 100:.2f}",
                        }
                    )

        # Le prix effectif : montant custom (prix libre) ou prix standard
        # Effective price: custom amount (free price) or standard price
        prix_en_centimes = custom_amount_centimes or int(round(prix_obj.prix * 100))

        articles_panier.append({
            'product': produit,
            'price': prix_obj,
            'quantite': quantite,
            'prix_centimes': prix_en_centimes,
            'custom_amount_centimes': custom_amount_centimes,
            'est_billet': est_billet,
            'event': event_billet,
        })

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
        total_centimes += article['prix_centimes'] * article['quantite']
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
        produit = article['product']
        prix_unitaire_euros = article['prix_centimes'] / 100
        quantite = article['quantite']
        prix_total_euros = prix_unitaire_euros * quantite

        if hasattr(produit, 'methode_caisse') and produit.methode_caisse in METHODES_RECHARGE:
            description = _("Recharge %(montant)s€ → carte de %(prenom)s") % {
                'montant': f"{prix_unitaire_euros:.2f}",
                'prenom': prenom_client,
            }
        elif produit.categorie_article == Product.ADHESION:
            description = _("%(nom_prix)s → rattachée à %(prenom)s %(nom)s") % {
                'nom_prix': article['price'].name,
                'prenom': prenom_client,
                'nom': nom_client.upper() if nom_client else "",
            }
        elif article.get('est_billet', False):
            event_name = article['event'].name if article.get('event') else "?"
            description = _("Billet %(nom)s — %(event)s") % {
                'nom': article['price'].name,
                'event': event_name,
            }
        else:
            description = f"{produit.name} × {quantite}"

        articles_pour_recapitulatif.append({
            'description': description,
            'prix_total_euros': prix_total_euros,
        })

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
    panier_a_recharges_payantes = articles_panier and _panier_contient_recharges_payantes(articles_panier)
    if not panier_a_recharges_payantes:
        moyens.append('nfc')

    if point_de_vente.accepte_especes:
        moyens.append('espece')

    if point_de_vente.accepte_carte_bancaire:
        moyens.append('carte_bancaire')

    if point_de_vente.accepte_cheque:
        moyens.append('CH')

    return moyens


def _creer_lignes_articles(
    articles_panier, code_methode_paiement,
    asset_uuid=None, carte=None, wallet=None,
    uuid_transaction=None, point_de_vente=None,
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
    methode_db = MAPPING_CODES_PAIEMENT.get(code_methode_paiement, PaymentMethod.UNKNOWN)

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
    for article in articles_panier:
        produit = article['product']
        prix_obj = article['price']
        quantite = article['quantite']
        prix_centimes = article['prix_centimes']

        # ProductSold : snapshot du produit au moment de la vente
        # ProductSold: product snapshot at the time of sale
        product_sold, _ = ProductSold.objects.get_or_create(
            product=produit,
            event=None,
            defaults={'categorie_article': produit.categorie_article},
        )

        # PriceSold : snapshot du prix au moment de la vente
        # PriceSold: price snapshot at the time of sale
        price_sold, _ = PriceSold.objects.get_or_create(
            productsold=product_sold,
            price=prix_obj,
            defaults={'prix': prix_obj.prix},
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
        )
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
        ligne_a_chainer.save(update_fields=['total_ht', 'hmac_hash', 'previous_hmac'])

        previous_hmac_value = ligne_a_chainer.hmac_hash

    return lignes_creees


def _creer_ou_renouveler_adhesion(user, product, price, contribution_value=None, first_name=None, last_name=None):
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

    valeur_contribution = contribution_value if contribution_value is not None else price.prix

    # Chercher une Membership existante pour ce user + price
    # Find an existing Membership for this user + price
    membership_existante = Membership.objects.filter(
        user=user,
        price=price,
    ).exclude(
        status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED],
    ).first()

    if membership_existante is not None:
        # Renouveler : mettre à jour la date de contribution et recalculer la deadline
        # Renew: update contribution date and recalculate deadline
        membership_existante.last_contribution = tz.now()
        membership_existante.status = Membership.LABOUTIK
        membership_existante.contribution_value = valeur_contribution
        champs_a_mettre_a_jour = ['last_contribution', 'status', 'contribution_value']
        if first_name:
            membership_existante.first_name = first_name
            champs_a_mettre_a_jour.append('first_name')
        if last_name:
            membership_existante.last_name = last_name
            champs_a_mettre_a_jour.append('last_name')
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
        a for a in articles_panier
        if a['product'].categorie_article == Product.ADHESION
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
        custom_centimes = article.get('custom_amount_centimes')
        if custom_centimes is not None:
            contribution = Decimal(custom_centimes) / 100
        else:
            contribution = article['price'].prix

        membership = _creer_ou_renouveler_adhesion(
            user=user_adhesion,
            product=article['product'],
            price=article['price'],
            contribution_value=contribution,
            first_name=prenom,
            last_name=nom,
        )

        # Rattacher la Membership a sa LigneArticle
        # / Link the Membership to its LigneArticle
        if membership:
            memberships_creees.append(membership)
            product_uuid = str(article['product'].uuid)
            ligne_correspondante = lignes_par_product.get(product_uuid)
            if ligne_correspondante:
                ligne_correspondante.membership = membership
                ligne_correspondante.save(update_fields=['membership'])

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
        if article.get('est_billet', False):
            articles_billet.append(article)

    if not articles_billet:
        return []

    # --- Recuperer le point de vente pour l'impression ---
    # / Get the point of sale for printing
    pv = None
    uuid_pv = request.POST.get("uuid_pv", "")
    if uuid_pv:
        try:
            pv = PointDeVente.objects.select_related('printer').get(uuid=uuid_pv)
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
        event = article.get('event')
        if event is None:
            logger.warning(f"Article billet sans event : {article['price'].name}")
            continue
        event_uuid = str(event.uuid)
        if event_uuid not in articles_par_event:
            articles_par_event[event_uuid] = {
                'event': event,
                'articles': [],
            }
        articles_par_event[event_uuid]['articles'].append(article)

    # --- Construire un index LigneArticle par product_uuid pour le rattachement ---
    # / Build a LigneArticle index by product_uuid for linking
    lignes_par_product = {}
    if lignes_articles:
        for ligne in lignes_articles:
            product_uuid = str(ligne.pricesold.productsold.product.uuid)
            lignes_par_product[product_uuid] = ligne

    reservations_creees = []

    for event_uuid, groupe in articles_par_event.items():
        event = groupe['event']
        articles_event = groupe['articles']

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
            total_billets_demandes += article_event['quantite']

        # Verifier la jauge globale de l'event
        # / Check the event's global gauge
        if jauge_max > 0 and places_vendues + total_billets_demandes > jauge_max:
            raise ValueError(
                _("Evenement %(event)s complet") % {'event': event.name}
            )

        # Verifier la jauge par tarif (Price.stock) si definie
        # / Check per-rate gauge (Price.stock) if defined
        for article in articles_event:
            price = article['price']
            quantite = article['quantite']
            if price.stock is not None and price.stock > 0:
                places_vendues_prix = Ticket.objects.filter(
                    reservation__event__pk=event.pk,
                    pricesold__price__pk=price.pk,
                    status__in=[Ticket.NOT_SCANNED, Ticket.SCANNED],
                ).count()
                if places_vendues_prix + quantite > price.stock:
                    raise ValueError(
                        _("Plus de places pour le tarif %(tarif)s") % {'tarif': price.name}
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
            product = article['product']
            price = article['price']
            quantite = article['quantite']

            # ProductSold avec event renseigne (contrairement aux ventes classiques)
            # / ProductSold with event set (unlike standard sales)
            product_sold, _created = ProductSold.objects.get_or_create(
                product=product,
                event=event_locked,
                defaults={'categorie_article': product.categorie_article},
            )

            # PriceSold
            price_sold, _created = PriceSold.objects.get_or_create(
                productsold=product_sold,
                price=price,
                defaults={'prix': price.prix},
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
                ligne_correspondante.save(update_fields=['reservation'])

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


def _executer_recharges(articles_panier, wallet_client, carte_client, code_methode_paiement, ip_client):
    """
    Exécute les recharges (RE/RC/TM) contenues dans le panier.
    Executes top-ups (RE/RC/TM) contained in the cart.

    LOCALISATION : laboutik/views.py

    DOIT être appelée à l'intérieur d'un bloc transaction.atomic().
    MUST be called inside a transaction.atomic() block.

    Pour chaque type de recharge :
    - Trouve l'asset correspondant (TLF, TNF, TIM) du tenant courant
    - Appelle TransactionService.creer_recharge(sender=wallet_lieu, receiver=wallet_client)
    - Crée les LigneArticle avec la carte et l'asset renseignés
    For each top-up type:
    - Finds the corresponding asset (TLF, TNF, TIM) of the current tenant
    - Calls TransactionService.creer_recharge(sender=venue_wallet, receiver=client_wallet)
    - Creates LigneArticle with the card and asset filled in

    :param articles_panier: liste de dicts (seulement les articles recharge)
    :param wallet_client: Wallet du client à créditer
    :param carte_client: CarteCashless du client
    :param code_methode_paiement: code du moyen de paiement ("espece", "carte_bancaire", "CH")
    :param ip_client: adresse IP de la requête
    :return: None
    :raises ValueError: si un asset requis n'est pas configuré
    """
    tenant_courant = connection.tenant

    # Classifier les recharges par type
    # Classify top-ups by type
    articles_re = []  # Recharge euros (TLF)
    articles_rc = []  # Recharge cadeau (TNF)
    articles_tm = []  # Recharge temps (TIM)

    for article in articles_panier:
        methode = article['product'].methode_caisse
        if methode == Product.RECHARGE_EUROS:
            articles_re.append(article)
        elif methode == Product.RECHARGE_CADEAU:
            articles_rc.append(article)
        elif methode == Product.RECHARGE_TEMPS:
            articles_tm.append(article)

    # Recharge euros (RE) → TLF : lieu → client
    # Euro top-up (RE) → TLF: venue → client
    if articles_re:
        asset_tlf = Asset.objects.filter(
            tenant_origin=tenant_courant,
            category=Asset.TLF,
            active=True,
        ).first()
        if asset_tlf is None:
            raise ValueError(_("Monnaie locale non configurée"))

        total_re = _calculer_total_panier_centimes(articles_re)
        TransactionService.creer_recharge(
            sender_wallet=asset_tlf.wallet_origin,
            receiver_wallet=wallet_client,
            asset=asset_tlf,
            montant_en_centimes=total_re,
            tenant=tenant_courant,
            ip=ip_client,
        )
        _creer_lignes_articles(
            articles_re, code_methode_paiement,
            asset_uuid=asset_tlf.uuid,
            carte=carte_client,
            wallet=wallet_client,
        )

    # Recharge cadeau (RC) → TNF : lieu → client
    # GRATUIT : le caissier offre du cadeau, pas de paiement.
    # Le payment_method est toujours FREE, quel que soit le moyen de paiement
    # choisi pour les autres articles du panier.
    # / Gift top-up (RC) → TNF: venue → client
    # FREE: the cashier gives a gift, no payment.
    # payment_method is always FREE regardless of the payment method
    # chosen for other items in the cart.
    if articles_rc:
        asset_tnf = Asset.objects.filter(
            tenant_origin=tenant_courant,
            category=Asset.TNF,
            active=True,
        ).first()
        if asset_tnf is None:
            raise ValueError(_("Monnaie cadeau non configurée"))

        total_rc = _calculer_total_panier_centimes(articles_rc)
        TransactionService.creer_recharge(
            sender_wallet=asset_tnf.wallet_origin,
            receiver_wallet=wallet_client,
            asset=asset_tnf,
            montant_en_centimes=total_rc,
            tenant=tenant_courant,
            ip=ip_client,
        )
        _creer_lignes_articles(
            articles_rc, "gift",
            asset_uuid=asset_tnf.uuid,
            carte=carte_client,
            wallet=wallet_client,
        )

    # Recharge temps (TM) → TIM : lieu → client
    # GRATUIT : meme logique que RC.
    # / Time top-up (TM) → TIM: venue → client
    # FREE: same logic as RC.
    if articles_tm:
        asset_tim = Asset.objects.filter(
            tenant_origin=tenant_courant,
            category=Asset.TIM,
            active=True,
        ).first()
        if asset_tim is None:
            raise ValueError(_("Monnaie temps non configurée"))

        total_tm = _calculer_total_panier_centimes(articles_tm)
        TransactionService.creer_recharge(
            sender_wallet=asset_tim.wallet_origin,
            receiver_wallet=wallet_client,
            asset=asset_tim,
            montant_en_centimes=total_tm,
            tenant=tenant_courant,
            ip=ip_client,
        )
        _creer_lignes_articles(
            articles_tm, "gift",
            asset_uuid=asset_tim.uuid,
            carte=carte_client,
            wallet=wallet_client,
        )


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
    permission_classes = [HasLaBoutikAccess]

    # ----------------------------------------------------------------------- #
    #  Étape 1 : afficher les moyens de paiement disponibles                   #
    #  Step 1: show available payment methods                                  #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["post"], url_path="moyens_paiement", url_name="moyens_paiement")
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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=404)

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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

        # --- Calculer le total en centimes puis convertir en euros ---
        # --- Calculate total in centimes then convert to euros ---
        total_centimes = _calculer_total_panier_centimes(articles_panier)
        total_en_euros = total_centimes / 100

        # --- Déterminer les moyens de paiement disponibles ---
        # --- Determine available payment methods ---
        # Si le panier contient des recharges (RE/RC/TM), NFC est exclu
        # If the cart contains top-ups (RE/RC/TM), NFC is excluded
        moyens_paiement_disponibles = _determiner_moyens_paiement(point_de_vente, articles_panier)

        # Si le panier contient des recharges, le template doit demander un scan NFC client
        # If the cart contains top-ups, the template must request a client NFC scan
        panier_a_recharges = _panier_contient_recharges(articles_panier)

        # Si le panier contient des adhésions, le template doit demander l'identification client
        # (scan NFC ou formulaire email/nom/prénom)
        # If the cart contains memberships, the template must request client identification
        # (NFC scan or email/name form)
        panier_a_adhesions = any(
            a['product'].categorie_article == Product.ADHESION
            for a in articles_panier
        )

        # Si le panier contient des billets, on demande aussi l'identification
        # (pour Reservation.user_commande). L'email est optionnel (to_mail).
        # / If the cart contains tickets, we also request identification
        # (for Reservation.user_commande). Email is optional (to_mail).
        panier_a_billets = False
        for article_panier in articles_panier:
            if article_panier.get('est_billet', False):
                panier_a_billets = True
                break

        # Le panier necessite un client si il contient des recharges, adhesions ou billets.
        # Dans ce cas, on demande une identification AVANT le choix du moyen de paiement.
        # / Cart requires a client if it contains top-ups, memberships or tickets.
        # In that case, we ask for identification BEFORE payment method choice.
        panier_necessite_client = panier_a_recharges or panier_a_adhesions or panier_a_billets

        # Liste des moyens de paiement en CSV pour propagation via templates HTMX
        # / Payment methods as CSV for propagation through HTMX templates
        moyens_paiement_csv = ",".join(moyens_paiement_disponibles)

        # Mode gérant : activé si la carte primaire est en mode édition
        # Manager mode: enabled if primary card is in edit mode
        est_mode_gerant = False

        # Une consigne dans le panier déclenche un flux de remboursement
        # A deposit in the basket triggers a refund flow
        uuids_articles_selectionnes = payment_method.extraire_uuids_articles(request.POST)
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
            "payment_translation": PAYMENT_METHOD_TRANSLATIONS.get(moyen_paiement_choisi, ""),
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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=404)

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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

        # --- Calculer le total en centimes ---
        # --- Calculate total in centimes ---
        uuids_articles_selectionnes = payment_method.extraire_uuids_articles(request.POST)
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
        logger.info(f"payer: moyen={moyen_paiement_code}, total={total_centimes}cts, articles={len(articles_panier)}")

        if moyen_paiement_code in ("carte_bancaire", "CH"):
            return self._payer_par_carte_ou_cheque(
                request, state, donnees_paiement, articles_panier,
                total_en_euros, total_centimes,
                consigne_dans_panier, transaction_precedente, moyen_paiement_code,
            )

        if moyen_paiement_code == "espece":
            return self._payer_en_especes(
                request, state, donnees_paiement, articles_panier,
                total_en_euros, total_centimes,
                consigne_dans_panier, transaction_precedente, moyen_paiement_code,
            )

        if moyen_paiement_code == "nfc":
            return self._payer_par_nfc(
                request, state, donnees_paiement, articles_panier,
                total_en_euros, total_centimes,
                consigne_dans_panier, moyen_paiement_code,
                point_de_vente,
            )

        # Moyen de paiement non reconnu → erreur
        # Unrecognized payment method → error
        context_erreur = {
            "msg_type": "warning",
            "msg_content": _("Il y a une erreur !"),
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

    # ------------------------------------------------------------------ #
    #  Flux de paiement : carte bancaire ou chèque                        #
    #  Payment flow: credit card or check                                 #
    # ------------------------------------------------------------------ #

    def _payer_par_carte_ou_cheque(
        self, request, state, donnees_paiement, articles_panier,
        total_en_euros, total_centimes,
        consigne_dans_panier, transaction_precedente, moyen_paiement_code,
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
        point_de_vente = PointDeVente.objects.select_related('printer').get(uuid=uuid_pv)

        # Identifiant unique de ce paiement — regroupe toutes les LigneArticle
        # / Unique ID for this payment — groups all LigneArticle records
        uuid_transaction = uuid_module.uuid4()

        # Séparer articles normaux et recharges
        # Separate normal articles and top-ups
        articles_normaux = [a for a in articles_panier if a['product'].methode_caisse not in METHODES_RECHARGE]
        articles_recharge = [a for a in articles_panier if a['product'].methode_caisse in METHODES_RECHARGE]
        reservations_billets = []

        with db_transaction.atomic():
            # Articles normaux (ventes, adhesions) → LigneArticle
            # Normal articles (sales, memberships) → LigneArticle
            lignes_normales = []
            if articles_normaux:
                lignes_normales = _creer_lignes_articles(
                    articles_normaux, moyen_paiement_code,
                    uuid_transaction=uuid_transaction,
                    point_de_vente=point_de_vente,
                )

            # Adhesions → creer les Memberships et les rattacher aux LigneArticle
            # Memberships → create Membership records and link them to LigneArticle
            _creer_adhesions_depuis_panier(request, articles_normaux, lignes_articles=lignes_normales)

            # Billets → creer Reservation + Tickets et rattacher aux LigneArticle
            # Tickets → create Reservation + Tickets and link them to LigneArticle
            reservations_billets = _creer_billets_depuis_panier(
                request, articles_normaux, lignes_articles=lignes_normales,
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
                    articles_recharge, wallet_client, carte_client,
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
        if (reservations_billets
                and point_de_vente.comportement == PointDeVente.BILLETTERIE
                and point_de_vente.printer
                and point_de_vente.printer.active):
            from BaseBillet.models import Ticket
            for reservation in reservations_billets:
                tickets_reservation = Ticket.objects.filter(
                    reservation=reservation,
                ).select_related('pricesold', 'reservation__event')
                for ticket_obj in tickets_reservation:
                    imprimer_billet(ticket_obj, reservation, reservation.event, point_de_vente)

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
        return render(request, "laboutik/partial/hx_return_payment_success.html", context)

    # ------------------------------------------------------------------ #
    #  Flux de paiement : espèces                                         #
    #  Payment flow: cash                                                 #
    # ------------------------------------------------------------------ #

    def _payer_en_especes(
        self, request, state, donnees_paiement, articles_panier,
        total_en_euros, total_centimes,
        consigne_dans_panier, transaction_precedente, moyen_paiement_code,
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
        point_de_vente = PointDeVente.objects.select_related('printer').get(uuid=uuid_pv)

        # La somme est suffisante si :
        # - le caissier n'a rien saisi (= paiement exact, pas de monnaie à rendre)
        # - ou la somme donnée couvre le total
        # The amount is sufficient if:
        # - the cashier entered nothing (= exact payment, no change to give)
        # - or the given sum covers the total
        somme_est_suffisante = (
            somme_donnee_en_centimes == 0
            or somme_donnee_en_centimes >= total_centimes
        )

        if somme_est_suffisante:
            ip_client = request.META.get("REMOTE_ADDR", "0.0.0.0")

            # Identifiant unique de ce paiement
            # / Unique ID for this payment
            uuid_transaction = uuid_module.uuid4()

            # Séparer articles normaux et recharges
            # Separate normal articles and top-ups
            articles_normaux = [a for a in articles_panier if a['product'].methode_caisse not in METHODES_RECHARGE]
            articles_recharge = [a for a in articles_panier if a['product'].methode_caisse in METHODES_RECHARGE]
            reservations_billets = []

            # Créer les lignes articles en base (atomique)
            # Create article lines in DB (atomic)
            with db_transaction.atomic():
                # Articles normaux (ventes, adhesions) → LigneArticle
                # Normal articles (sales, memberships) → LigneArticle
                lignes_normales = []
                if articles_normaux:
                    lignes_normales = _creer_lignes_articles(
                        articles_normaux, moyen_paiement_code,
                        uuid_transaction=uuid_transaction,
                        point_de_vente=point_de_vente,
                    )

                # Adhesions → creer les Memberships et les rattacher aux LigneArticle
                # Memberships → create Membership records and link them to LigneArticle
                _creer_adhesions_depuis_panier(request, articles_normaux, lignes_articles=lignes_normales)

                # Billets → creer Reservation + Tickets et rattacher aux LigneArticle
                # Tickets → create Reservation + Tickets and link them to LigneArticle
                reservations_billets = _creer_billets_depuis_panier(
                    request, articles_normaux, lignes_articles=lignes_normales,
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
                        articles_recharge, wallet_client, carte_client,
                        code_methode_paiement=moyen_paiement_code,
                        ip_client=ip_client,
                    )

            # Apres le bloc atomic : envoyer les billets par email via Celery
            # / After the atomic block: send tickets by email via Celery
            if reservations_billets:
                _envoyer_billets_par_email(reservations_billets)

            # Impression automatique des billets pour le PV BILLETTERIE
            # / Auto-print tickets for ticketing POS
            if (reservations_billets
                    and point_de_vente.comportement == PointDeVente.BILLETTERIE
                    and point_de_vente.printer
                    and point_de_vente.printer.active):
                for reservation in reservations_billets:
                    tickets_reservation = Ticket.objects.filter(
                        reservation=reservation,
                    ).select_related('pricesold', 'reservation__event')
                    for ticket_obj in tickets_reservation:
                        imprimer_billet(ticket_obj, reservation, reservation.event, point_de_vente)

            # Calculer la monnaie à rendre (en euros)
            # Calculate change to give back (in euros)
            donnees_paiement["give_back"] = 0
            if somme_donnee_en_centimes > total_centimes:
                donnees_paiement["give_back"] = (somme_donnee_en_centimes - total_centimes) / 100

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
            return render(request, "laboutik/partial/hx_return_payment_success.html", context)

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
        self, request, state, donnees_paiement, articles_panier,
        total_en_euros, total_centimes,
        consigne_dans_panier, moyen_paiement_code,
        point_de_vente,
    ):
        """
        Paiement NFC (cashless) via fedow_core.
        NFC (cashless) payment via fedow_core.

        LOCALISATION : laboutik/views.py

        Flux complet / Full flow:
        1. Chercher la carte client par tag_id
        2. Déterminer le wallet client (user.wallet ou wallet_ephemere)
        3. Trouver l'asset TLF du tenant
        4. Classifier les articles par methode_caisse (VT, RE, RC, TM, AD)
        5. Vérifier le solde pour les articles qui débitent le client (VT + AD)
        6. Bloc atomic : ventes + recharges + adhésions
        7. Succès : afficher nouveau solde
        """
        # GARDE : le paiement NFC est interdit si le panier contient des recharges PAYANTES (RE).
        # Les recharges gratuites (RC/TM) sont auto-creditees et ne bloquent pas le NFC.
        # / GUARD: NFC payment forbidden if cart has PAID top-ups (RE).
        # Free top-ups (RC/TM) are auto-credited and don't block NFC.
        if _panier_contient_recharges_payantes(articles_panier):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Les recharges ne peuvent pas être payées en cashless"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

        tag_id_client = request.POST.get("tag_id", "").upper().strip()

        # 1. Chercher la carte client par tag_id
        # 1. Find client card by tag_id
        try:
            carte_client = CarteCashless.objects.get(tag_id=tag_id_client)
        except CarteCashless.DoesNotExist:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Carte inconnue"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur)

        # 2. Déterminer le wallet client (get or create éphémère si besoin)
        # 2. Determine client wallet (get or create ephemeral if needed)
        wallet_client = _obtenir_ou_creer_wallet(carte_client)

        # 3. Trouver l'asset TLF actif du tenant
        # 3. Find the tenant's active TLF asset
        asset_tlf = Asset.objects.filter(
            tenant_origin=connection.tenant,
            category=Asset.TLF,
            active=True,
        ).first()

        if asset_tlf is None:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Monnaie locale non configurée"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur)

        wallet_lieu = asset_tlf.wallet_origin

        # 4. Classifier les articles en 3 categories :
        #    - Ventes (VT) : debitent le wallet du client en TLF
        #    - Adhesions (AD) : debitent le wallet du client en TLF + creent un Membership
        #    - Recharges gratuites (RC/TM) : creditent le wallet du client (pas de debit)
        #    Les recharges payantes (RE) sont bloquees par la garde ci-dessus.
        # / 4. Classify articles into 3 categories:
        #    - Sales (VT): debit the client's wallet in TLF
        #    - Memberships (AD): debit the client's wallet in TLF + create a Membership
        #    - Free top-ups (RC/TM): credit the client's wallet (no debit)
        #    Paid top-ups (RE) are blocked by the guard above.
        articles_vente = []
        articles_adhesion = []
        articles_recharge_gratuite = []

        for article in articles_panier:
            methode = article['product'].methode_caisse
            if article['product'].categorie_article == Product.ADHESION:
                articles_adhesion.append(article)
            elif methode in METHODES_RECHARGE_GRATUITES:
                # RC (cadeau) ou TM (temps) : credit gratuit, pas de debit
                # / RC (gift) or TM (time): free credit, no debit
                articles_recharge_gratuite.append(article)
            else:
                # Vente classique (VT ou tout autre type)
                # / Standard sale (VT or any other type)
                articles_vente.append(article)

        total_vente_centimes = _calculer_total_panier_centimes(articles_vente)
        total_adhesion_centimes = _calculer_total_panier_centimes(articles_adhesion)

        # Le montant qui debite le client = ventes + adhesions.
        # Les recharges gratuites (RC/TM) ne debitent PAS le client.
        # / Amount that debits the client = sales + memberships.
        # Free top-ups (RC/TM) do NOT debit the client.
        total_debit_client_centimes = total_vente_centimes + total_adhesion_centimes

        # 5. Vérifier le solde AVANT le bloc atomic (rejet rapide, sans verrou)
        #    Seuls VT + AD débitent le client. RE/RC/TM le créditent.
        # 5. Check balance BEFORE atomic block (fast reject, no lock)
        #    Only VT + AD debit the client. RE/RC/TM credit the client.
        if total_debit_client_centimes > 0:
            solde_client = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf)
            if solde_client < total_debit_client_centimes:
                montant_manquant = total_debit_client_centimes - solde_client
                donnees_paiement["missing"] = montant_manquant / 100
                context_insuffisant = {
                    "currency_data": CURRENCY_DATA,
                    "payment": donnees_paiement,
                    "card": {"name": carte_client.tag_id},
                    "monnaie_name": asset_tlf.name,
                    "payments_accepted": {
                        "accepte_especes": point_de_vente.accepte_especes,
                        "accepte_carte_bancaire": point_de_vente.accepte_carte_bancaire,
                    },
                    "uuid_transaction": "",
                }
                return render(request, "laboutik/partial/hx_funds_insufficient.html", context_insuffisant)

        # 6. Bloc atomic : ventes + adhésions (pas de recharges en NFC)
        # 6. Atomic block: sales + memberships (no top-ups in NFC)
        ip_client = request.META.get("REMOTE_ADDR", "0.0.0.0")
        tenant_courant = connection.tenant

        # Identifiant unique de ce paiement
        # / Unique ID for this payment
        uuid_transaction = uuid_module.uuid4()

        try:
            with db_transaction.atomic():
                # a) Ventes (VT) — client → lieu
                # a) Sales (VT) — client → venue
                if total_vente_centimes > 0:
                    TransactionService.creer_vente(
                        sender_wallet=wallet_client,
                        receiver_wallet=wallet_lieu,
                        asset=asset_tlf,
                        montant_en_centimes=total_vente_centimes,
                        tenant=tenant_courant,
                        card=carte_client,
                        ip=ip_client,
                    )
                    _creer_lignes_articles(
                        articles_vente, moyen_paiement_code,
                        asset_uuid=asset_tlf.uuid,
                        carte=carte_client,
                        wallet=wallet_client,
                        uuid_transaction=uuid_transaction,
                        point_de_vente=point_de_vente,
                    )

                # b) Adhésions (AD) — débit tokens TLF + création Membership
                # b) Memberships (AD) — debit TLF tokens + create Membership
                if total_adhesion_centimes > 0:
                    TransactionService.creer_vente(
                        sender_wallet=wallet_client,
                        receiver_wallet=wallet_lieu,
                        asset=asset_tlf,
                        montant_en_centimes=total_adhesion_centimes,
                        tenant=tenant_courant,
                        card=carte_client,
                        ip=ip_client,
                    )
                    lignes_adhesion = _creer_lignes_articles(
                        articles_adhesion, moyen_paiement_code,
                        asset_uuid=asset_tlf.uuid,
                        carte=carte_client,
                        wallet=wallet_client,
                        uuid_transaction=uuid_transaction,
                        point_de_vente=point_de_vente,
                    )

                # c) Recharges gratuites (RC/TM) — credit wallet client, pas de debit
                #    Meme logique que dans _payer_en_especes : _executer_recharges
                #    avec code "gift" → PaymentMethod.FREE.
                # / c) Free top-ups (RC/TM) — credit client wallet, no debit
                #    Same logic as _payer_en_especes: _executer_recharges
                #    with "gift" code → PaymentMethod.FREE.
                if articles_recharge_gratuite:
                    _executer_recharges(
                        articles_recharge_gratuite, wallet_client, carte_client,
                        code_methode_paiement="gift",
                        ip_client=ip_client,
                    )

                # Creer/renouveler les adhesions et rattacher aux LigneArticle
                # Create/renew memberships and link to LigneArticle
                if articles_adhesion:
                    # Construire un index LigneArticle par product_uuid
                    # / Build LigneArticle index by product_uuid
                    lignes_par_product = {}
                    for ligne in lignes_adhesion:
                        product_uuid = str(ligne.pricesold.productsold.product.uuid)
                        lignes_par_product[product_uuid] = ligne

                    for article in articles_adhesion:
                        membership = _creer_ou_renouveler_adhesion(
                            carte_client.user,
                            article['product'],
                            article['price'],
                        )
                        # Rattacher la Membership a sa LigneArticle
                        # / Link the Membership to its LigneArticle
                        if membership:
                            product_uuid = str(article['product'].uuid)
                            ligne = lignes_par_product.get(product_uuid)
                            if ligne:
                                ligne.membership = membership
                                ligne.save(update_fields=['membership'])

        except SoldeInsuffisant:
            # Race condition : solde a changé entre le check et le débit
            # Race condition: balance changed between check and debit
            solde_restant = WalletService.obtenir_solde(
                wallet=wallet_client, asset=asset_tlf,
            )
            montant_manquant = total_debit_client_centimes - solde_restant
            donnees_paiement["missing"] = montant_manquant / 100
            context_insuffisant = {
                "currency_data": CURRENCY_DATA,
                "payment": donnees_paiement,
                "card": {"name": carte_client.tag_id},
                "monnaie_name": asset_tlf.name,
                "payments_accepted": {
                    "accepte_especes": point_de_vente.accepte_especes,
                    "accepte_carte_bancaire": point_de_vente.accepte_carte_bancaire,
                },
                "uuid_transaction": "",
            }
            return render(request, "laboutik/partial/hx_funds_insufficient.html", context_insuffisant)

        # 7. Succès : lire le nouveau solde et afficher
        # 7. Success: read new balance and display
        nouveau_solde_centimes = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf)
        nouveau_solde_euros = nouveau_solde_centimes / 100

        context = {
            "currency_data": CURRENCY_DATA,
            "payment": donnees_paiement,
            "monnaie_name": asset_tlf.name,
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
        }
        return render(request, "laboutik/partial/hx_return_payment_success.html", context)

    # ----------------------------------------------------------------------- #
    #  Flow identification client : identification obligatoire avant paiement  #
    #  Client identification flow: mandatory identification before payment     #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["get"], url_path="lire_nfc_client", url_name="lire_nfc_client")
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

    @action(detail=False, methods=["get"], url_path="formulaire_identification_client", url_name="formulaire_identification_client")
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
        return render(request, "laboutik/partial/hx_formulaire_identification_client.html", context)

    @action(detail=False, methods=["post"], url_path="identifier_client", url_name="identifier_client")
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
        moyens_paiement = [m.strip() for m in moyens_paiement_csv.split(",") if m.strip()]

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
                articles_panier = _extraire_articles_du_panier(request.POST, point_de_vente)
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
                return render(request, "laboutik/partial/hx_messages.html", context_erreur)

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
                return render(request, "laboutik/partial/hx_formulaire_identification_client.html", context)

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
        panier_uniquement_gratuit = _panier_contient_uniquement_recharges_gratuites(articles_panier)
        if carte and panier_uniquement_gratuit:
            ip_client = request.META.get("REMOTE_ADDR", "0.0.0.0")
            wallet_client = _obtenir_ou_creer_wallet(carte)

            with db_transaction.atomic():
                _executer_recharges(
                    articles_panier, wallet_client, carte,
                    code_methode_paiement="gift",
                    ip_client=ip_client,
                )

            # Calculer le solde apres credit pour l'ecran de succes
            # / Compute balance after credit for the success screen
            solde_apres = 0
            try:
                solde_apres = WalletService.obtenir_total_en_centimes(wallet_client) / 100
            except Exception:
                pass

            # Construire le recapitulatif des articles credites
            # / Build the recap of credited items
            carte_label = carte.tag_id
            if user:
                carte_label = user.first_name or carte.tag_id
            articles_pour_recapitulatif = _construire_recapitulatif_articles(
                articles_panier, carte_label, "",
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
            return render(request, "laboutik/partial/hx_return_payment_success.html", context)

        # User identifie → ecran recapitulatif avec articles et boutons de paiement
        # / User identified → recap screen with articles and payment buttons
        if user:
            solde = 0
            if hasattr(user, 'wallet') and user.wallet:
                try:
                    solde = WalletService.obtenir_total_en_centimes(user.wallet) / 100
                except Exception:
                    solde = 0

            user_prenom = user.first_name or prenom
            user_nom = user.last_name or nom

            # Enrichir les articles avec un texte adaptatif par type
            # / Enrich articles with adaptive text per type
            articles_pour_recapitulatif = _construire_recapitulatif_articles(
                articles_panier, user_prenom, user_nom,
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
            return render(request, "laboutik/partial/hx_recapitulatif_client.html", context)

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
                return render(request, "laboutik/partial/hx_formulaire_identification_client.html", context)

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
                    solde_carte = WalletService.obtenir_total_en_centimes(carte.wallet_ephemere) / 100
                except Exception:
                    solde_carte = 0
            elif carte.user and hasattr(carte.user, 'wallet') and carte.user.wallet:
                try:
                    solde_carte = WalletService.obtenir_total_en_centimes(carte.user.wallet) / 100
                except Exception:
                    solde_carte = 0

            carte_label = carte.tag_id
            articles_pour_recapitulatif = _construire_recapitulatif_articles(
                articles_panier, carte_label, "",
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
            return render(request, "laboutik/partial/hx_recapitulatif_client.html", context)

        # Aucune info → formulaire vierge
        # / No info → blank form
        context = {
            "panier_a_recharges": panier_a_recharges,
            "panier_a_adhesions": panier_a_adhesions,
            "panier_a_billets": panier_a_billets,
            "moyens_paiement_csv": moyens_paiement_csv,
        }
        return render(request, "laboutik/partial/hx_formulaire_identification_client.html", context)

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

    @action(detail=False, methods=["get"], url_path="verifier_carte", url_name="verifier_carte")
    def verifier_carte(self, request):
        """
        GET /laboutik/paiement/verifier_carte/
        Affiche le partial d'attente de lecture NFC (pour vérification de solde).
        Displays the NFC read waiting partial (for balance check).
        """
        return render(request, "laboutik/partial/hx_check_card.html", {})

    @action(detail=False, methods=["post"], url_path="retour_carte", url_name="retour_carte")
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
            tokens.append({
                'asset_name': t.asset.name,
                'asset_category': t.asset.category,
                'value_euros': t.value / 100,
                'provenance': t.asset.tenant_origin.name,
            })
            total_centimes += t.value
            if t.asset.category == Asset.TLF:
                solde_tlf_centimes += t.value
            elif t.asset.category == Asset.TNF:
                solde_tnf_centimes += t.value

        # 4. Adhésions actives (si user connu)
        # 4. Active memberships (if user known)
        adhesions = []
        if carte.user:
            toutes_adhesions = list(Membership.objects.filter(
                user=carte.user,
            ).exclude(
                status__in=[Membership.CANCELED, Membership.ADMIN_CANCELED],
            ).select_related('price__product'))
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

    # ------------------------------------------------------------------ #
    #  Impression ticket de vente (bouton sur l'ecran de succes)           #
    #  Sale receipt printing (button on the success screen)                #
    # ------------------------------------------------------------------ #

    @action(detail=False, methods=["post"], url_path="imprimer_ticket", url_name="imprimer_ticket")
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
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Donnees manquantes pour l'impression"),
                "selector_bt_retour": "#print-feedback",
            })

        # Recuperer le PV et son imprimante
        # / Get the POS and its printer
        try:
            point_de_vente = PointDeVente.objects.select_related('printer').get(uuid=uuid_pv)
        except (PointDeVente.DoesNotExist, ValueError):
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Point de vente introuvable"),
                "selector_bt_retour": "#print-feedback",
            })

        if not point_de_vente.printer or not point_de_vente.printer.active:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Aucune imprimante configuree pour ce point de vente"),
                "selector_bt_retour": "#print-feedback",
            })

        # Recuperer les lignes de cette transaction
        # / Get the lines for this transaction
        lignes_du_paiement = LigneArticle.objects.filter(
            uuid_transaction=uuid_transaction_str,
        ).select_related('pricesold__productsold')

        if not lignes_du_paiement.exists():
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Aucune ligne trouvee pour cette transaction"),
                "selector_bt_retour": "#print-feedback",
            })

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
            lignes_du_paiement, point_de_vente, operateur, moyen_paiement,
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

    @action(detail=False, methods=["get"], url_path="formulaire_correction", url_name="formulaire_correction")
    def formulaire_correction(self, request):
        """
        GET /laboutik/paiement/formulaire_correction/?ligne_uuid=...
        Affiche le formulaire de correction de moyen de paiement.
        / Shows the payment method correction form.

        LOCALISATION : laboutik/views.py
        """
        ligne_uuid = request.GET.get("ligne_uuid")
        if not ligne_uuid:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Ligne d'article introuvable"),
            }, status=400)

        try:
            ligne = LigneArticle.objects.get(uuid=ligne_uuid)
        except (LigneArticle.DoesNotExist, ValueError):
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Ligne d'article introuvable"),
            }, status=404)

        # Liste des moyens corrigeables (ESP/CB/CHQ), sans le moyen actuel
        # / List of correctable methods (CASH/CC/CHECK), without the current one
        moyens_corrigeables = []
        if ligne.payment_method != PaymentMethod.CASH:
            moyens_corrigeables.append({"code": PaymentMethod.CASH, "label": _("Especes")})
        if ligne.payment_method != PaymentMethod.CC:
            moyens_corrigeables.append({"code": PaymentMethod.CC, "label": _("Carte bancaire")})
        if ligne.payment_method != PaymentMethod.CHEQUE:
            moyens_corrigeables.append({"code": PaymentMethod.CHEQUE, "label": _("Cheque")})

        # Label humain du moyen actuel + montant en euros pour l'affichage
        # / Human label of current method + amount in euros for display
        moyen_actuel_label = LABELS_MOYENS_PAIEMENT_DB.get(ligne.payment_method, ligne.payment_method)
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
        return render(request, "laboutik/partial/hx_corriger_moyen_paiement.html", context)

    @action(detail=False, methods=["post"], url_path="corriger_moyen_paiement", url_name="corriger_moyen_paiement")
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
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": str(premiere_erreur),
            }, status=400)

        ligne_uuid = serializer.validated_data['ligne_uuid']
        nouveau_moyen = serializer.validated_data['nouveau_moyen']
        raison = serializer.validated_data['raison']

        # --- Recuperer la ligne d'article ---
        # / Get the article line
        try:
            ligne = LigneArticle.objects.get(uuid=ligne_uuid)
        except LigneArticle.DoesNotExist:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Ligne d'article introuvable"),
            }, status=404)

        # --- GARDE 1 : les paiements NFC (cashless) ne peuvent pas etre corriges ---
        # Les paiements cashless sont lies a des Transactions fedow_core.
        # Modifier le moyen de paiement casserait la coherence avec le registre fedow.
        # / NFC payments are linked to fedow_core Transactions.
        # Changing the method would break coherence with the fedow ledger.
        moyens_nfc = (PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT)
        if ligne.payment_method in moyens_nfc:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Les paiements cashless ne peuvent pas etre modifies"),
            }, status=400)

        # --- GARDE 2 : post-cloture interdit ---
        # Les lignes couvertes par une cloture journaliere sont immuables.
        # / Lines covered by a daily closure are immutable.
        cloture_existante = ligne_couverte_par_cloture(ligne)
        if cloture_existante:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Cette vente est couverte par une cloture. Modification interdite."),
            }, status=400)

        # --- GARDE 3 : meme moyen = pas de correction ---
        # / Same method = no correction needed
        if ligne.payment_method == nouveau_moyen:
            return render(request, "laboutik/partial/hx_messages.html", {
                "msg_type": "warning",
                "msg_content": _("Le moyen de paiement est deja identique"),
            }, status=400)

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
                ligne_a_corriger.save(update_fields=['payment_method'])
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
        nouveau_moyen_label = LABELS_MOYENS_PAIEMENT_DB.get(nouveau_moyen, nouveau_moyen)

        return render(request, "laboutik/partial/hx_correction_succes.html", {
            "ancien_moyen_label": ancien_moyen_label,
            "nouveau_moyen_label": nouveau_moyen_label,
            "ligne_uuid": str(ligne.uuid),
            "uuid_transaction": str(ligne.uuid_transaction) if ligne.uuid_transaction else str(ligne.uuid),
        })


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
    permission_classes = [HasLaBoutikAccess]

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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=404)

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
                return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=404)

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
                prix = Price.objects.get(uuid=article_data["price_uuid"], product=produit)
            except Price.DoesNotExist:
                logger.warning(
                    f"ouvrir_commande: prix {article_data['price_uuid']} non trouvé pour {produit.name}"
                )
                continue

            articles_valides.append({
                "product": produit,
                "price": prix,
                "qty": article_data["qty"],
            })

        if not articles_valides:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Aucun article valide dans la commande"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

        # Bloc atomique : table → commande → articles
        # Atomic block: table → order → articles
        with db_transaction.atomic():
            # Marquer la table comme occupée
            # Mark table as occupied
            if table_obj is not None:
                table_obj.statut = Table.OCCUPEE
                table_obj.save(update_fields=['statut'])

            # Créer la commande
            # Create the order
            commande = CommandeSauvegarde.objects.create(
                table=table_obj,
                statut=CommandeSauvegarde.OPEN,
                responsable=request.user if request.user.is_authenticated else None,
                commentaire='',
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

    @action(detail=False, methods=["post"], url_path="ajouter/(?P<commande_uuid>[^/.]+)", url_name="ajouter")
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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=404)

        # Vérifier que la commande est encore ouverte
        # Check that the order is still open
        if commande.statut != CommandeSauvegarde.OPEN:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Cette commande n'est plus ouverte"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

        articles_data = serializer.validated_data

        if not articles_data:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Aucun article fourni"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

        # Créer les articles dans un bloc atomique
        # Create articles in an atomic block
        with db_transaction.atomic():
            for article_data in articles_data:
                try:
                    produit = Product.objects.get(uuid=article_data["product_uuid"])
                    prix = Price.objects.get(uuid=article_data["price_uuid"], product=produit)
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

    @action(detail=False, methods=["post"], url_path="servir/(?P<commande_uuid>[^/.]+)", url_name="servir")
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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=404)

        if commande.statut not in (CommandeSauvegarde.OPEN, CommandeSauvegarde.SERVED):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Cette commande ne peut pas être marquée comme servie"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

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
            commande.save(update_fields=['statut'])

            # Mettre à jour le statut de la table
            # Update table status
            if commande.table is not None:
                commande.table.statut = Table.SERVIE
                commande.table.save(update_fields=['statut'])

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

    @action(detail=False, methods=["post"], url_path="payer/(?P<commande_uuid>[^/.]+)", url_name="payer")
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
            commande = CommandeSauvegarde.objects.select_related('table').get(uuid=commande_uuid)
        except (CommandeSauvegarde.DoesNotExist, ValueError):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Commande introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=404)

        if commande.statut not in (CommandeSauvegarde.OPEN, CommandeSauvegarde.SERVED):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Cette commande ne peut pas être payée"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

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
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=404)

        # Construire articles_panier depuis les articles de la commande
        # Build articles_panier from order articles
        articles_commande = commande.articles.filter(
            statut__in=[
                ArticleCommandeSauvegarde.EN_ATTENTE,
                ArticleCommandeSauvegarde.EN_COURS,
                ArticleCommandeSauvegarde.PRET,
                ArticleCommandeSauvegarde.SERVI,
            ],
        ).select_related('product', 'price')

        articles_panier = []
        for article_cmd in articles_commande:
            prix_centimes = int(round(article_cmd.price.prix * 100))
            articles_panier.append({
                'product': article_cmd.product,
                'price': article_cmd.price,
                'quantite': article_cmd.qty,
                'prix_centimes': prix_centimes,
            })

        if not articles_panier:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Aucun article à payer dans cette commande"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

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
                    request, state, donnees_paiement, articles_panier,
                    total_en_euros, total_centimes,
                    False, moyen_paiement_code,
                    point_de_vente,
                )

                # Détecter le succès NFC via le data-testid dans le HTML
                # Detect NFC success via data-testid in the HTML
                nfc_paiement_reussi = b'paiement-succes' in response_nfc.content

                if not nfc_paiement_reussi:
                    # Fonds insuffisants, carte inconnue, etc.
                    # Le savepoint interne a déjà rollback.
                    # Insufficient funds, unknown card, etc.
                    # The inner savepoint already rolled back.
                    return response_nfc

                # NFC réussi → mettre à jour commande + table
                # NFC succeeded → update order + table
                commande.statut = CommandeSauvegarde.PAID
                commande.save(update_fields=['statut'])

                commande.articles.exclude(
                    statut=ArticleCommandeSauvegarde.ANNULE,
                ).update(
                    statut=ArticleCommandeSauvegarde.SERVI,
                    reste_a_payer=0,
                    reste_a_servir=0,
                )

                if commande.table is not None:
                    autres_commandes_ouvertes = CommandeSauvegarde.objects.filter(
                        table=commande.table,
                        statut__in=[CommandeSauvegarde.OPEN, CommandeSauvegarde.SERVED],
                    ).exclude(uuid=commande.uuid).exists()
                    if not autres_commandes_ouvertes:
                        commande.table.statut = Table.LIBRE
                        commande.table.save(update_fields=['statut'])

            return response_nfc

        # --- Paiement non-NFC (espèces, CB, chèque) ---
        # --- Non-NFC payment (cash, CC, check) ---
        with db_transaction.atomic():
            _creer_lignes_articles(
                articles_panier, moyen_paiement_code,
                point_de_vente=point_de_vente,
            )

            # Marquer la commande comme payée
            # Mark order as paid
            commande.statut = CommandeSauvegarde.PAID
            commande.save(update_fields=['statut'])

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
                autres_commandes_ouvertes = CommandeSauvegarde.objects.filter(
                    table=commande.table,
                    statut__in=[CommandeSauvegarde.OPEN, CommandeSauvegarde.SERVED],
                ).exclude(uuid=commande.uuid).exists()

                if not autres_commandes_ouvertes:
                    commande.table.statut = Table.LIBRE
                    commande.table.save(update_fields=['statut'])

        # Construire la réponse succès pour espèces/CB/chèque
        # Build success response for cash/CC/check
        donnees_paiement["give_back"] = 0
        if moyen_paiement_code == "espece" and donnees_paiement["given_sum"] > total_centimes:
            donnees_paiement["give_back"] = (donnees_paiement["given_sum"] - total_centimes) / 100

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
        return render(request, "laboutik/partial/hx_return_payment_success.html", context)

    # ----------------------------------------------------------------------- #
    #  5. Annuler une commande                                                 #
    #  5. Cancel an order                                                      #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["post"], url_path="annuler/(?P<commande_uuid>[^/.]+)", url_name="annuler")
    def annuler_commande(self, request, commande_uuid=None):
        """
        POST /laboutik/commande/annuler/<commande_uuid>/
        Annule la commande et libère la table si nécessaire.
        Cancels the order and frees the table if needed.
        """
        try:
            commande = CommandeSauvegarde.objects.select_related('table').get(uuid=commande_uuid)
        except (CommandeSauvegarde.DoesNotExist, ValueError):
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Commande introuvable"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=404)

        if commande.statut == CommandeSauvegarde.PAID:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Une commande payée ne peut pas être annulée"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

        with db_transaction.atomic():
            # Annuler la commande et ses articles
            # Cancel the order and its articles
            commande.statut = CommandeSauvegarde.CANCEL
            commande.save(update_fields=['statut'])

            commande.articles.exclude(
                statut=ArticleCommandeSauvegarde.ANNULE,
            ).update(statut=ArticleCommandeSauvegarde.ANNULE)

            # Libérer la table si pas d'autre commande ouverte dessus
            # Free the table if no other open order on it
            if commande.table is not None:
                autres_commandes_ouvertes = CommandeSauvegarde.objects.filter(
                    table=commande.table,
                    statut__in=[CommandeSauvegarde.OPEN, CommandeSauvegarde.SERVED],
                ).exclude(uuid=commande.uuid).exists()

                if not autres_commandes_ouvertes:
                    commande.table.statut = Table.LIBRE
                    commande.table.save(update_fields=['statut'])

        context = {
            "msg_type": "success",
            "msg_content": _("Commande annulée"),
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context)
