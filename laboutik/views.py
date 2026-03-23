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
from django.db.models import Prefetch, Sum, Count, Q

from fedow_core.exceptions import SoldeInsuffisant
from fedow_core.models import Asset
from fedow_core.services import TransactionService, WalletService

from AuthBillet.models import Wallet
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import (
    Configuration, LigneArticle, Membership, Price, PriceSold, Product,
    ProductSold, SaleOrigin, PaymentMethod,
)
from BaseBillet.permissions import HasLaBoutikAccess
from QrcodeCashless.models import CarteCashless
from laboutik.models import (
    LaboutikConfiguration,
    PointDeVente, CartePrimaire, Table,
    CommandeSauvegarde, ArticleCommandeSauvegarde,
    ClotureCaisse,
)
from laboutik.serializers import (
    AdhesionIdentificationSerializer,
    CartePrimaireSerializer, PanierSerializer,
    CommandeSerializer, ArticleCommandeSerializer,
    ClotureSerializer, EnvoyerRapportSerializer,
)
from laboutik.utils import method as payment_method


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
    produits = (
        point_de_vente_instance.products
        .filter(Q(methode_caisse__isnull=False) | Q(categorie_article=Product.ADHESION))
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


# Constantes : methodes de caisse qui représentent des recharges cashless
# Constants: POS methods that represent cashless top-ups
METHODES_RECHARGE = (Product.RECHARGE_EUROS, Product.RECHARGE_CADEAU, Product.RECHARGE_TEMPS)


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
        Cloture le service en cours : calcule les totaux, ferme les tables, cree le rapport.
        Closes the current service: calculates totals, closes tables, creates the report.

        LOCALISATION : laboutik/views.py

        FLUX / FLOW :
        1. Valider avec ClotureSerializer (datetime_ouverture + uuid_pv)
        2. Agreger les LigneArticle par moyen de paiement (depuis datetime_ouverture)
        3. Construire le rapport JSON (par categorie, produit, moyen de paiement, commandes)
        4. Creer ClotureCaisse
        5. Fermer tables ouvertes et commandes OPEN
        6. Retourner le rapport (template partial)
        """
        serializer = ClotureSerializer(data=request.data)
        if not serializer.is_valid():
            premiere_erreur = next(iter(serializer.errors.values()))[0]
            context_erreur = {
                "msg_type": "warning",
                "msg_content": str(premiere_erreur),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur, status=400)

        datetime_ouverture = serializer.validated_data["datetime_ouverture"]
        uuid_pv = serializer.validated_data["uuid_pv"]

        # --- Vérifier que la carte primaire a accès au PV ---
        # --- Check that the primary card has access to the PV ---
        tag_id_carte_manager = request.POST.get("tag_id_cm", "")
        _valider_carte_primaire_pour_pv(tag_id_carte_manager, uuid_pv)

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

        # --- Filtrer les LigneArticle de la periode ---
        # --- Filter LigneArticle for the period ---
        lignes_periode = LigneArticle.objects.filter(
            sale_origin=SaleOrigin.LABOUTIK,
            datetime__gte=datetime_ouverture,
            status=LigneArticle.VALID,
        )

        # --- Calculer les totaux par moyen de paiement (en centimes) ---
        # --- Calculate totals by payment method (in cents) ---
        total_especes = lignes_periode.filter(
            payment_method=PaymentMethod.CASH,
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_carte_bancaire = lignes_periode.filter(
            payment_method=PaymentMethod.CC,
        ).aggregate(total=Sum('amount'))['total'] or 0

        # NFC / cashless : LOCAL_EURO (monnaie fiduciaire) + LOCAL_GIFT (cadeau)
        # NFC / cashless: LOCAL_EURO (fiat) + LOCAL_GIFT (gift)
        total_cashless = lignes_periode.filter(
            payment_method__in=[PaymentMethod.LOCAL_EURO, PaymentMethod.LOCAL_GIFT],
        ).aggregate(total=Sum('amount'))['total'] or 0

        total_general = total_especes + total_carte_bancaire + total_cashless
        nombre_transactions = lignes_periode.count()

        # --- Construire le rapport JSON ---
        # --- Build the JSON report ---

        # Par moyen de paiement / By payment method
        rapport_par_moyen_paiement = {
            "especes": total_especes,
            "cb": total_carte_bancaire,
            "nfc": total_cashless,
        }

        # Par produit / By product
        # Agreger par nom de produit via PriceSold → ProductSold → Product
        # Aggregate by product name via PriceSold → ProductSold → Product
        rapport_par_produit = {}
        produits_agreg = lignes_periode.values(
            'pricesold__productsold__product__name',
        ).annotate(
            total_amount=Sum('amount'),
            total_qty=Sum('qty'),
        ).order_by('pricesold__productsold__product__name')

        for ligne in produits_agreg:
            nom_produit = ligne['pricesold__productsold__product__name'] or _("Inconnu")
            rapport_par_produit[nom_produit] = {
                "total": ligne['total_amount'] or 0,
                "qty": float(ligne['total_qty'] or 0),
            }

        # Par categorie / By category
        # Agreger par categorie POS du produit
        # Aggregate by product POS category
        rapport_par_categorie = {}
        categories_agreg = lignes_periode.values(
            'pricesold__productsold__product__categorie_pos__name',
        ).annotate(
            total_amount=Sum('amount'),
        ).order_by('pricesold__productsold__product__categorie_pos__name')

        for ligne in categories_agreg:
            nom_categorie = ligne['pricesold__productsold__product__categorie_pos__name'] or _("Sans catégorie")
            rapport_par_categorie[str(nom_categorie)] = ligne['total_amount'] or 0

        # Par taux de TVA / By VAT rate
        # Agreger par taux de TVA — calcule HT et TVA depuis le TTC (amount) et le taux (vat)
        # Aggregate by VAT rate — compute HT and VAT from TTC (amount) and rate (vat)
        rapport_par_tva = {}
        tva_agreg = lignes_periode.values('vat').annotate(
            total_ttc=Sum('amount'),
        ).order_by('vat')

        for ligne in tva_agreg:
            taux_tva = float(ligne['vat'] or 0)
            total_ttc_centimes = ligne['total_ttc'] or 0

            # Calcul du HT depuis le TTC : HT = TTC / (1 + taux/100)
            # Calculate HT from TTC: HT = TTC / (1 + rate/100)
            if taux_tva > 0:
                total_ht_centimes = int(round(total_ttc_centimes / (1 + taux_tva / 100)))
                total_tva_centimes = total_ttc_centimes - total_ht_centimes
            else:
                total_ht_centimes = total_ttc_centimes
                total_tva_centimes = 0

            cle_tva = f"{taux_tva:.2f}%"
            rapport_par_tva[cle_tva] = {
                "taux": taux_tva,
                "total_ttc": total_ttc_centimes,
                "total_ht": total_ht_centimes,
                "total_tva": total_tva_centimes,
            }

        # Commandes / Orders
        commandes_total = CommandeSauvegarde.objects.filter(
            datetime__gte=datetime_ouverture,
        ).count()
        commandes_annulees = CommandeSauvegarde.objects.filter(
            datetime__gte=datetime_ouverture,
            statut=CommandeSauvegarde.CANCEL,
        ).count()
        rapport_commandes = {
            "total": commandes_total,
            "annulees": commandes_annulees,
        }

        rapport_json = {
            "par_categorie": rapport_par_categorie,
            "par_produit": rapport_par_produit,
            "par_moyen_paiement": rapport_par_moyen_paiement,
            "par_tva": rapport_par_tva,
            "commandes": rapport_commandes,
        }

        # --- Creer la ClotureCaisse ---
        # --- Create the ClotureCaisse ---
        cloture = ClotureCaisse.objects.create(
            point_de_vente=point_de_vente,
            responsable=request.user if request.user.is_authenticated else None,
            datetime_ouverture=datetime_ouverture,
            total_especes=total_especes,
            total_carte_bancaire=total_carte_bancaire,
            total_cashless=total_cashless,
            total_general=total_general,
            nombre_transactions=nombre_transactions,
            rapport_json=rapport_json,
        )

        # --- Fermer les tables ouvertes (OCCUPEE ou SERVIE → LIBRE) ---
        # --- Close open tables (OCCUPIED or SERVED → FREE) ---
        Table.objects.filter(
            statut__in=[Table.OCCUPEE, Table.SERVIE],
        ).update(statut=Table.LIBRE)

        # --- Annuler les commandes encore ouvertes ---
        # --- Cancel still-open orders ---
        CommandeSauvegarde.objects.filter(
            statut=CommandeSauvegarde.OPEN,
        ).update(statut=CommandeSauvegarde.CANCEL)

        logger.info(
            f"Cloture caisse: PV={point_de_vente.name}, "
            f"total={total_general}cts, transactions={nombre_transactions}"
        )

        # --- Convertir la TVA en euros pour l'affichage ---
        # --- Convert VAT to euros for display ---
        rapport_tva_euros = {}
        for taux_label, tva_data in rapport_par_tva.items():
            rapport_tva_euros[taux_label] = {
                "total_ht_euros": f"{tva_data['total_ht'] / 100:.2f}",
                "total_tva_euros": f"{tva_data['total_tva'] / 100:.2f}",
                "total_ttc_euros": f"{tva_data['total_ttc'] / 100:.2f}",
            }

        # --- Retourner le rapport ---
        # --- Return the report ---
        context = {
            "cloture": cloture,
            "rapport": rapport_json,
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


def _determiner_moyens_paiement(point_de_vente, articles_panier=None):
    """
    Détermine les moyens de paiement disponibles selon la config du PV et le panier.
    Determines available payment methods based on PV config and cart contents.

    LOCALISATION : laboutik/views.py

    RÈGLE MÉTIER : si le panier contient des recharges (RE/RC/TM), le paiement NFC
    est interdit. Une recharge cashless ne peut pas être payée en cashless.
    BUSINESS RULE: if the cart contains top-ups (RE/RC/TM), NFC payment is forbidden.
    A cashless top-up cannot be paid with cashless.

    :param point_de_vente: instance PointDeVente
    :param articles_panier: liste de dicts retournée par _extraire_articles_du_panier() (optionnel)
    :return: liste de codes moyens de paiement (ex: ["nfc", "espece", "carte_bancaire"])
    """
    moyens = []

    # NFC interdit si le panier contient des recharges
    # NFC forbidden if the cart contains top-ups
    panier_a_recharges = articles_panier and _panier_contient_recharges(articles_panier)
    if not panier_a_recharges:
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
            # Champs NFC (optionnels, None pour espèces/CB)
            # NFC fields (optional, None for cash/CC)
            asset=asset_uuid,
            carte=carte,
            wallet=wallet,
        )
        lignes_creees.append(ligne)

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
    # Gift top-up (RC) → TNF: venue → client
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
            articles_rc, code_methode_paiement,
            asset_uuid=asset_tnf.uuid,
            carte=carte_client,
            wallet=wallet_client,
        )

    # Recharge temps (TM) → TIM : lieu → client
    # Time top-up (TM) → TIM: venue → client
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
            articles_tm, code_methode_paiement,
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
            "panier_a_recharges": panier_a_recharges,
            "panier_a_adhesions": panier_a_adhesions,
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

        # Séparer articles normaux et recharges
        # Separate normal articles and top-ups
        articles_normaux = [a for a in articles_panier if a['product'].methode_caisse not in METHODES_RECHARGE]
        articles_recharge = [a for a in articles_panier if a['product'].methode_caisse in METHODES_RECHARGE]

        with db_transaction.atomic():
            # Articles normaux (ventes, adhesions) → LigneArticle
            # Normal articles (sales, memberships) → LigneArticle
            lignes_normales = []
            if articles_normaux:
                lignes_normales = _creer_lignes_articles(articles_normaux, moyen_paiement_code)

            # Adhesions → creer les Memberships et les rattacher aux LigneArticle
            # Memberships → create Membership records and link them to LigneArticle
            _creer_adhesions_depuis_panier(request, articles_normaux, lignes_articles=lignes_normales)

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
            ip_client = request.META.get("REMOTE_ADDR", "0.0.0.0")

            # Séparer articles normaux et recharges
            # Separate normal articles and top-ups
            articles_normaux = [a for a in articles_panier if a['product'].methode_caisse not in METHODES_RECHARGE]
            articles_recharge = [a for a in articles_panier if a['product'].methode_caisse in METHODES_RECHARGE]

            # Créer les lignes articles en base (atomique)
            # Create article lines in DB (atomic)
            with db_transaction.atomic():
                # Articles normaux (ventes, adhesions) → LigneArticle
                # Normal articles (sales, memberships) → LigneArticle
                lignes_normales = []
                if articles_normaux:
                    lignes_normales = _creer_lignes_articles(articles_normaux, moyen_paiement_code)

                # Adhesions → creer les Memberships et les rattacher aux LigneArticle
                # Memberships → create Membership records and link them to LigneArticle
                _creer_adhesions_depuis_panier(request, articles_normaux, lignes_articles=lignes_normales)

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
        # GARDE : le paiement NFC est interdit si le panier contient des recharges
        # GUARD: NFC payment is forbidden if the cart contains top-ups
        if _panier_contient_recharges(articles_panier):
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

        # 4. Classifier les articles : adhesion (categorie_article=ADHESION) vs vente
        #    NFC = seulement ventes et adhesions. Les recharges sont rejetées par la garde.
        # 4. Classify articles: membership (categorie_article=ADHESION) vs sale
        #    NFC = only sales and memberships. Top-ups are rejected by the guard.
        articles_vente = []
        articles_adhesion = []

        for article in articles_panier:
            if article['product'].categorie_article == Product.ADHESION:
                articles_adhesion.append(article)
            else:
                # Vente classique (VT ou tout autre type)
                # / Standard sale (VT or any other type)
                articles_vente.append(article)

        total_vente_centimes = _calculer_total_panier_centimes(articles_vente)
        total_adhesion_centimes = _calculer_total_panier_centimes(articles_adhesion)

        # Le montant qui débite le client = ventes + adhésions
        # Amount that debits the client = sales + memberships
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
        }
        return render(request, "laboutik/partial/hx_return_payment_success.html", context)

    # ----------------------------------------------------------------------- #
    #  Flow adhésion : identification obligatoire avant paiement               #
    #  Membership flow: mandatory identification before payment                #
    # ----------------------------------------------------------------------- #

    @action(detail=False, methods=["get"], url_path="adhesion_choisir_identification", url_name="adhesion_choisir_identification")
    def adhesion_choisir_identification(self, request):
        """
        GET /laboutik/paiement/adhesion_choisir_identification/?method=espece
        Ecran : "Scanner carte TiBillet" ou "Saisir email / nom".
        Affiché après le choix espèce/CB/chèque pour une adhésion.
        / Screen: "Scan TiBillet card" or "Enter email / name".
        Shown after cash/CB/check choice for a membership.
        """
        method = request.GET.get("method", "espece")
        context = {"method": method}
        return render(request, "laboutik/partial/hx_adhesion_choose_id.html", context)

    @action(detail=False, methods=["get"], url_path="lire_nfc_adhesion", url_name="lire_nfc_adhesion")
    def lire_nfc_adhesion(self, request):
        """
        GET /laboutik/paiement/lire_nfc_adhesion/?method=nfc
        Attente NFC pour adhésion. Après scan, POST vers identifier_membre.
        / NFC read wait for membership. After scan, POST to identifier_membre.
        """
        method = request.GET.get("method", "nfc")
        context = {"method": method}
        return render(request, "laboutik/partial/hx_read_nfc_adhesion.html", context)

    @action(detail=False, methods=["get"], url_path="adhesion_formulaire", url_name="adhesion_formulaire")
    def adhesion_formulaire(self, request):
        """
        GET /laboutik/paiement/adhesion_formulaire/?method=espece
        Affiche le formulaire email/nom/prénom vierge.
        / Displays the blank email/name form.
        """
        method = request.GET.get("method", "espece")
        context = {"moyen_paiement": method}
        return render(request, "laboutik/partial/hx_adhesion_form.html", context)

    @action(detail=False, methods=["post"], url_path="identifier_membre", url_name="identifier_membre")
    def identifier_membre(self, request):
        """
        POST /laboutik/paiement/identifier_membre/

        Reçoit tag_id (scan NFC) OU email/nom/prénom (formulaire).
        Retourne :
        - Si user identifié → hx_adhesion_confirm.html (résumé + CONFIRMER)
        - Si carte anonyme → hx_adhesion_form.html (formulaire pré-rempli avec tag_id)
        - Si formulaire soumis avec email → validation puis hx_adhesion_confirm.html

        Receives tag_id (NFC scan) OR email/name (form).
        Returns:
        - If user identified → hx_adhesion_confirm.html (summary + CONFIRM)
        - If anonymous card → hx_adhesion_form.html (pre-filled form with tag_id)
        - If form submitted with email → validation then hx_adhesion_confirm.html
        """
        tag_id = request.POST.get("tag_id", "").upper().strip()
        email = request.POST.get("email_adhesion", "").strip().lower()
        prenom = request.POST.get("prenom_adhesion", "").strip()
        nom = request.POST.get("nom_adhesion", "").strip()
        moyen_paiement = request.POST.get("moyen_paiement", "nfc")

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
            serializer = AdhesionIdentificationSerializer(data=request.POST)
            if not serializer.is_valid():
                # Première erreur trouvée pour l'affichage
                # / First error found for display
                premiere_erreur = ""
                for champ, erreurs in serializer.errors.items():
                    premiere_erreur = erreurs[0]
                    break
                context = {
                    "moyen_paiement": moyen_paiement,
                    "tag_id": tag_id,
                    "email": email,
                    "prenom": prenom,
                    "nom": nom,
                    "erreur": premiere_erreur,
                }
                return render(request, "laboutik/partial/hx_adhesion_form.html", context)

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

        # User identifié → écran confirmation
        # / User identified → confirmation screen
        if user:
            solde = 0
            if hasattr(user, 'wallet') and user.wallet:
                try:
                    solde = WalletService.obtenir_total_en_centimes(user.wallet) / 100
                except Exception:
                    solde = 0

            context = {
                "user_email": user.email,
                "user_prenom": user.first_name or prenom,
                "user_nom": user.last_name or nom,
                "user_solde": solde,
                "tag_id": tag_id,
                "moyen_paiement": moyen_paiement,
            }
            return render(request, "laboutik/partial/hx_adhesion_confirm.html", context)

        # Carte anonyme (scan NFC mais pas de user) → formulaire avec tag_id
        # / Anonymous card (NFC scan but no user) → form with tag_id
        if carte and not user:
            context = {
                "tag_id": tag_id,
                "moyen_paiement": moyen_paiement,
            }
            return render(request, "laboutik/partial/hx_adhesion_form.html", context)

        # Aucune info → formulaire vierge
        # / No info → blank form
        context = {"moyen_paiement": moyen_paiement}
        return render(request, "laboutik/partial/hx_adhesion_form.html", context)

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
            _creer_lignes_articles(articles_panier, moyen_paiement_code)

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
