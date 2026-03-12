# laboutik/views.py
# ViewSets DRF pour l'interface de caisse LaBoutik (POS tactile).
# DRF ViewSets for the LaBoutik cash register interface (touch POS).
#
# Authentification : clé API LaBoutik (Discovery / PIN pairing) ou session admin tenant.
# Authentication: LaBoutik API key (Discovery / PIN pairing) or tenant admin session.
#
# CaisseViewSet : données depuis la DB (modèles ORM).
# PaiementViewSet : paiements espèces/CB depuis la DB (Phase 2). NFC encore placeholder (Phase 3).

import logging
import os
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

from django.db.models import Prefetch

from BaseBillet.models import (
    Configuration, LigneArticle, Price, PriceSold, Product,
    ProductSold, SaleOrigin, PaymentMethod,
)
from BaseBillet.permissions import HasLaBoutikAccess
from QrcodeCashless.models import CarteCashless
from laboutik.models import PointDeVente, CartePrimaire, Table
from laboutik.serializers import CartePrimaireSerializer, PanierSerializer
from laboutik.utils import mockData
from laboutik.utils import method as payment_method


# --------------------------------------------------------------------------- #
#  Constantes                                                                  #
# --------------------------------------------------------------------------- #

# Chemin vers la base de données JSON mock (utilisé par PaiementViewSet)
# Path to the mock JSON database (used by PaiementViewSet)
MOCK_DB_PATH = os.path.join(os.path.dirname(__file__), "utils", "mockDb.json")

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

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Fonctions utilitaires — état, articles, catégories                         #
#  Utility functions — state, articles, categories                            #
# --------------------------------------------------------------------------- #

def _construire_state(point_de_vente=None, carte_primaire_obj=None):
    """
    Construit le dictionnaire "state" à chaque requête.
    Builds the "state" dictionary on each request.

    Le state est lu côté client (JS) via stateJson pour piloter l'interface.
    State is read client-side (JS) via stateJson to drive the interface.
    """
    config = Configuration.get_solo()
    state = {
        "version": "0.9.11",
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
    produits = (
        point_de_vente_instance.products
        .filter(methode_caisse__isnull=False)
        .select_related('categorie_pos')
        .prefetch_related(prix_euros_prefetch)
        .order_by('poids', 'name')
    )

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
            categorie_dict = {
                "id": str(categorie_pos.uuid),
                "name": categorie_pos.name,
                "icon": categorie_pos.icon or "fa-angry",
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

        article_dict = {
            "id": str(product.uuid),
            "name": product.name,
            "prix": prix_en_centimes,
            "categorie": categorie_dict,
            "bt_groupement": {
                "groupe": product.groupe_pos or f"groupe_{product.methode_caisse or 'VT'}",
            },
            "url_image": url_image,
        }
        articles.append(article_dict)

    return articles


def _construire_donnees_categories(point_de_vente_instance):
    """
    Construit la liste de dicts catégories au format attendu par les templates.
    Builds the list of category dicts in the format expected by templates.
    """
    categories_qs = point_de_vente_instance.categories.order_by('poid_liste', 'name')
    categories = []
    for categorie in categories_qs:
        categories.append({
            "id": str(categorie.uuid),
            "name": categorie.name,
            "icon": categorie.icon or "fa-th",
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


# --------------------------------------------------------------------------- #
#  Fonctions utilitaires mock — utilisées uniquement par PaiementViewSet      #
#  Mock utility functions — used only by PaiementViewSet                      #
# --------------------------------------------------------------------------- #

def _charger_mock_db():
    """
    Charge la base de données JSON mock (PaiementViewSet uniquement).
    Loads the mock JSON database (PaiementViewSet only).
    """
    return mockData.mockDb(MOCK_DB_PATH)


def _charger_points_de_vente():
    """
    Charge les points de vente mock (PaiementViewSet uniquement).
    Loads mock points of sale (PaiementViewSet only).
    """
    return mockData.get_data_pvs()


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

        # Mode kiosk (borne libre-service) → template spécifique
        # Kiosk mode (self-service terminal) → specific template
        if pv.comportement == PointDeVente.KIOSK:
            template_name = "laboutik/views/kiosk.html"

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
        }
        return render(request, template_name, context)


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
}


def _extraire_articles_du_panier(donnees_post, point_de_vente):
    """
    Extrait les articles du formulaire POST et les charge depuis la DB.
    Extracts articles from the POST form and loads them from DB.

    LOCALISATION : laboutik/views.py

    Le formulaire d'addition envoie les quantités avec les clés "repid-<uuid>".
    Pour chaque article, on charge le Product et son premier prix publié en euros.
    The addition form sends quantities with "repid-<uuid>" keys.
    For each article, we load the Product and its first published EUR price.

    :param donnees_post: QueryDict ou dict des données POST
    :param point_de_vente: instance PointDeVente (pour filtrer les produits autorisés)
    :return: liste de dicts {'product': Product, 'price': Price, 'quantite': int, 'prix_centimes': int}
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
    produits_du_pv = {
        str(p.uuid): p
        for p in point_de_vente.products
        .filter(methode_caisse__isnull=False)
        .prefetch_related(prix_euros_prefetch)
    }

    articles_panier = []
    for article_data in articles_extraits:
        uuid_str = article_data['uuid']
        quantite = article_data['quantite']

        produit = produits_du_pv.get(uuid_str)
        if produit is None:
            logger.warning(f"Produit {uuid_str} non trouvé dans le PV {point_de_vente.name}")
            continue

        if not produit.prix_euros:
            logger.warning(f"Produit {produit.name} n'a pas de prix EUR publié")
            continue

        prix_obj = produit.prix_euros[0]
        prix_en_centimes = int(round(prix_obj.prix * 100))

        articles_panier.append({
            'product': produit,
            'price': prix_obj,
            'quantite': quantite,
            'prix_centimes': prix_en_centimes,
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


def _determiner_moyens_paiement(point_de_vente):
    """
    Détermine les moyens de paiement disponibles selon la config du PV.
    Determines available payment methods based on PV configuration.

    NFC (cashless) est toujours proposé si le PV n'est pas en mode cashless pur.
    Le vrai paiement NFC sera implémenté en Phase 3.
    NFC (cashless) is always offered unless the PV is in pure cashless mode.
    Actual NFC payment will be implemented in Phase 3.

    :param point_de_vente: instance PointDeVente
    :return: liste de codes moyens de paiement (ex: ["nfc", "espece", "carte_bancaire"])
    """
    moyens = []

    # NFC toujours proposé (géré en Phase 3)
    # NFC always offered (handled in Phase 3)
    moyens.append('nfc')

    if point_de_vente.accepte_especes:
        moyens.append('espece')

    if point_de_vente.accepte_carte_bancaire:
        moyens.append('carte_bancaire')

    if point_de_vente.accepte_cheque:
        moyens.append('CH')

    return moyens


def _creer_lignes_articles(articles_panier, code_methode_paiement):
    """
    Crée ProductSold, PriceSold et LigneArticle pour chaque article du panier.
    Creates ProductSold, PriceSold and LigneArticle for each article in the cart.

    LOCALISATION : laboutik/views.py

    Cette fonction est appelée dans un bloc transaction.atomic() par les fonctions
    de paiement (_payer_par_carte_ou_cheque, _payer_en_especes).
    This function is called inside a transaction.atomic() block by the payment
    functions (_payer_par_carte_ou_cheque, _payer_en_especes).

    :param articles_panier: liste de dicts retournée par _extraire_articles_du_panier()
    :param code_methode_paiement: code du moyen de paiement ("carte_bancaire", "espece", "CH")
    :return: liste de LigneArticle créées
    """
    methode_db = MAPPING_CODES_PAIEMENT.get(code_methode_paiement, PaymentMethod.UNKNOWN)

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
            sale_origin=SaleOrigin.LABOUTIK,
            payment_method=methode_db,
            status=LigneArticle.VALID,
        )
        lignes_creees.append(ligne)

    return lignes_creees


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

        state = _construire_state(point_de_vente)

        # --- Extraire les articles du panier depuis le POST ---
        # --- Extract cart articles from POST ---
        articles_panier = _extraire_articles_du_panier(request.POST, point_de_vente)

        # --- Calculer le total en centimes puis convertir en euros ---
        # --- Calculate total in centimes then convert to euros ---
        total_centimes = _calculer_total_panier_centimes(articles_panier)
        total_en_euros = total_centimes / 100

        # --- Déterminer les moyens de paiement disponibles ---
        # --- Determine available payment methods ---
        moyens_paiement_disponibles = _determiner_moyens_paiement(point_de_vente)

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
            "currency_data": CURRENCY_DATA,
            "total": total_en_euros,
            "mode_gerant": est_mode_gerant,
            "deposit_is_present": consigne_dans_panier,
            "comportement": point_de_vente.comportement,
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
        total_a_payer = request.GET.get("total")
        uuid_transaction = request.GET.get("uuid_transaction", "")

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
        articles_panier = _extraire_articles_du_panier(request.POST, point_de_vente)

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
                request, state, donnees_paiement,
                total_en_euros, consigne_dans_panier, moyen_paiement_code,
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
        No server-side verification (the card terminal or check is handled externally).
        We create LigneArticle records in DB then display success.
        """
        # Créer les lignes articles en base (atomique)
        # Create article lines in DB (atomic)
        with db_transaction.atomic():
            _creer_lignes_articles(articles_panier, moyen_paiement_code)

        # Le total dans donnees_paiement reste en centimes pour le template
        # (le filtre divide_by:100 convertit en euros pour l'affichage)
        # Total in donnees_paiement stays in centimes for the template
        # (the divide_by:100 filter converts to euros for display)
        context = {
            "currency_data": CURRENCY_DATA,
            "payment": donnees_paiement,
            "monnaie_name": state["place"]["monnaie_name"],
            "moyen_paiement": PAYMENT_METHOD_TRANSLATIONS.get(moyen_paiement_code, ""),
            "deposit_is_present": consigne_dans_panier,
            "total": total_en_euros,
            "state": state,
            "original_payment": transaction_precedente,
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
            # Créer les lignes articles en base (atomique)
            # Create article lines in DB (atomic)
            with db_transaction.atomic():
                _creer_lignes_articles(articles_panier, moyen_paiement_code)

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
        self, request, state, donnees_paiement,
        total_en_euros, consigne_dans_panier, moyen_paiement_code,
    ):
        """
        Paiement NFC (cashless) — Phase 3, pas encore implémenté.
        NFC (cashless) payment — Phase 3, not yet implemented.

        LOCALISATION : laboutik/views.py

        Retourne un message indiquant que le paiement NFC sera disponible
        dans une prochaine mise à jour (intégration fedow_core).
        Returns a message indicating that NFC payment will be available
        in a future update (fedow_core integration).
        """
        context_erreur = {
            "msg_type": "warning",
            "msg_content": _("Paiement NFC disponible en prochaine mise à jour"),
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context_erreur)

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
        solde, type (fédérée/anonyme), couleur de fond selon le statut.
        Receives the scanned NFC tag and returns card feedback:
        balance, type (federated/anonymous), background color based on status.
        """
        state = _construire_state()
        db = _charger_mock_db()
        tag_id_scanne = request.POST.get("tag_id", "").upper()

        # Couleur de fond par défaut : succès (carte connue avec email)
        # Default background color: success (known card with email)
        couleur_fond = "--success"

        cartes_trouvees = db.get_by_index("cards", "tag_id", tag_id_scanne)
        if not cartes_trouvees:
            # Carte inconnue → fond rouge
            # Unknown card → red background
            carte = {"type_card": "unknown", "wallets": 0, "wallets_gift": 0, "email": None}
            couleur_fond = "--error"
        else:
            carte = cartes_trouvees[0]
            if carte.get("email") is None:
                # Carte anonyme (pas d'email associé) → fond orange
                # Anonymous card (no associated email) → orange background
                couleur_fond = "--warning"

        context = {
            "card": carte,
            "total_monnaie": carte["wallets"] + carte["wallets_gift"],
            "tag_id": tag_id_scanne,
            "background": couleur_fond,
            "state": state,
        }
        return render(request, "laboutik/partial/hx_card_feedback.html", context)
