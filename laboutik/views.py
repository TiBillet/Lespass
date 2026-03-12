# laboutik/views.py
# ViewSets DRF pour l'interface de caisse LaBoutik (POS tactile).
# DRF ViewSets for the LaBoutik cash register interface (touch POS).
#
# Authentification : clé API LaBoutik (Discovery / PIN pairing) ou session admin tenant.
# Authentication: LaBoutik API key (Discovery / PIN pairing) or tenant admin session.
#
# CaisseViewSet : données depuis la DB (modèles ORM).
# PaiementViewSet : données encore mockées (JSON fichier, étape 2).

import logging
import os
from json import dumps

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django_htmx.http import HttpResponseClientRedirect
from rest_framework import viewsets
from rest_framework.decorators import action

from django.db.models import Prefetch

from BaseBillet.models import Configuration, Price
from BaseBillet.permissions import HasLaBoutikAccess
from QrcodeCashless.models import CarteCashless
from laboutik.models import PointDeVente, CartePrimaire, Table
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
        tag_id_carte_manager = request.POST.get("tag_id", "").upper()
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
#  PaiementViewSet — HTMX partials du flux de paiement                        #
# --------------------------------------------------------------------------- #

class PaiementViewSet(viewsets.ViewSet):
    """
    Partials HTMX pour le flux de paiement de la caisse.
    HTMX partials for the cash register payment flow.

    Flux de paiement (3 étapes) / Payment flow (3 steps) :
    1. moyens_paiement() → affiche les boutons de paiement disponibles / shows available payment buttons
    2. confirmer()       → écran de confirmation + saisie espèce / confirmation screen + cash input
    3. payer()           → exécute le paiement (mock) + retour succès ou fonds insuffisants
                           executes payment (mock) + returns success or insufficient funds

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
        state = _construire_state()
        tous_les_points_de_vente = _charger_points_de_vente()

        uuid_pv = request.POST.get("uuid_pv")
        uuids_articles_selectionnes = payment_method.extraire_uuids_articles(request.POST)
        point_de_vente = mockData.get_pv_from_uuid(uuid_pv, tous_les_points_de_vente)

        moyens_paiement_disponibles = payment_method.selectionner_moyens_paiement(
            point_de_vente, uuids_articles_selectionnes, request.POST,
        )
        total_addition = payment_method.calculer_total_addition(
            point_de_vente, uuids_articles_selectionnes, request.POST,
        )

        # Mode gérant désactivé pour l'instant (mock)
        # Manager mode disabled for now (mock)
        est_mode_gerant = False

        # Une consigne dans le panier déclenche un flux de remboursement
        # A deposit in the basket triggers a refund flow
        consigne_dans_panier = UUID_ARTICLE_CONSIGNE in uuids_articles_selectionnes
        if consigne_dans_panier:
            total_addition = abs(total_addition)

        context = {
            "state": state,
            "moyens_paiement": moyens_paiement_disponibles,
            "currency_data": CURRENCY_DATA,
            "total": total_addition,
            "mode_gerant": est_mode_gerant,
            "deposit_is_present": consigne_dans_panier,
            "comportement": point_de_vente["comportement"],
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
        Exécute le paiement mock selon le moyen choisi.
        Executes the mock payment according to the chosen method.

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
        state = _construire_state()
        db = _charger_mock_db()
        tous_les_points_de_vente = _charger_points_de_vente()

        uuids_articles_selectionnes = payment_method.extraire_uuids_articles(request.POST)
        donnees_paiement = request.POST.dict()

        # --- Normaliser les montants (les champs texte du formulaire → entiers) ---
        # --- Normalize amounts (form text fields → integers) ---
        donnees_paiement["total"] = int(donnees_paiement.get("total", 0))
        somme_donnee_brute = donnees_paiement.get("given_sum", "")
        if somme_donnee_brute == "":
            donnees_paiement["given_sum"] = 0
        else:
            donnees_paiement["given_sum"] = int(somme_donnee_brute)
        donnees_paiement["missing"] = 0

        # --- Calculer le total de l'addition ---
        # --- Calculate the addition total ---
        consigne_dans_panier = UUID_ARTICLE_CONSIGNE in uuids_articles_selectionnes
        point_de_vente = mockData.get_pv_from_uuid(
            donnees_paiement.get("uuid_pv"), tous_les_points_de_vente,
        )
        total_addition = payment_method.calculer_total_addition(
            point_de_vente, uuids_articles_selectionnes, request.POST,
        )
        # Les consignes ont un prix négatif (remboursement), on prend la valeur absolue
        # Deposits have a negative price (refund), we take the absolute value
        if consigne_dans_panier:
            total_addition = abs(total_addition)

        # --- Chercher une transaction précédente (complément après fonds insuffisants) ---
        # --- Look for a previous transaction (top-up after insufficient funds) ---
        # Quand un paiement NFC échoue par manque de fonds, on sauvegarde la transaction.
        # Le caissier peut ensuite compléter par espèces ou CB. Le uuid_transaction
        # permet de retrouver le premier versement.
        # When an NFC payment fails due to lack of funds, we save the transaction.
        # The cashier can then complete with cash or credit card. The uuid_transaction
        # lets us find the first payment.
        transaction_precedente = None
        uuid_transaction_precedente = donnees_paiement.get("uuid_transaction", "")
        if uuid_transaction_precedente != "":
            resultats_recherche = db.get_by_index(
                "transactions", "id", uuid_transaction_precedente,
            )
            if resultats_recherche and len(resultats_recherche) == 1:
                transaction_precedente = resultats_recherche[0]

        # --- Aiguillage vers le bon flux de paiement ---
        # --- Route to the correct payment flow ---
        moyen_paiement_code = donnees_paiement.get("moyen_paiement", "")
        logger.info(f"moyen_paiement_code: {moyen_paiement_code}")

        if moyen_paiement_code in ("carte_bancaire", "CH"):
            return self._payer_par_carte_ou_cheque(
                request, state, donnees_paiement, total_addition,
                consigne_dans_panier, transaction_precedente, moyen_paiement_code,
            )

        if moyen_paiement_code == "espece":
            return self._payer_en_especes(
                request, state, donnees_paiement, total_addition,
                consigne_dans_panier, transaction_precedente, moyen_paiement_code,
            )

        if moyen_paiement_code == "nfc":
            return self._payer_par_nfc(
                request, state, db, donnees_paiement, point_de_vente,
                total_addition, consigne_dans_panier, transaction_precedente,
                moyen_paiement_code,
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
        self, request, state, donnees_paiement, total_addition,
        consigne_dans_panier, transaction_precedente, moyen_paiement_code,
    ):
        """
        Paiement par carte bancaire ("carte_bancaire") ou chèque ("CH").
        Credit card or check payment.

        Pas de vérification côté serveur (le TPE ou le chèque est géré en dehors).
        On affiche directement le succès.
        No server-side verification (the card terminal or check is handled externally).
        We directly display success.
        """
        # Convertir le total de centimes en euros pour l'affichage
        # Convert total from cents to euros for display
        donnees_paiement["total"] = donnees_paiement["total"] / 100

        context = {
            "currency_data": CURRENCY_DATA,
            "payment": donnees_paiement,
            "monnaie_name": state["place"]["monnaie_name"],
            "moyen_paiement": PAYMENT_METHOD_TRANSLATIONS.get(moyen_paiement_code, ""),
            "deposit_is_present": consigne_dans_panier,
            "total": total_addition,
            "state": state,
            "original_payment": transaction_precedente,
        }
        return render(request, "laboutik/partial/hx_return_payment_success.html", context)

    # ------------------------------------------------------------------ #
    #  Flux de paiement : espèces                                         #
    #  Payment flow: cash                                                 #
    # ------------------------------------------------------------------ #

    def _payer_en_especes(
        self, request, state, donnees_paiement, total_addition,
        consigne_dans_panier, transaction_precedente, moyen_paiement_code,
    ):
        """
        Paiement en espèces.
        Cash payment.

        Deux cas :
        1. Paiement exact (given_sum vide ou == 0) → succès immédiat
        2. Le caissier saisit la somme donnée → on calcule la monnaie à rendre

        Si c'est un complément (après fonds insuffisants NFC), on prend en compte
        le montant déjà payé lors de la première transaction.

        Two cases:
        1. Exact payment (given_sum empty or == 0) → immediate success
        2. The cashier enters the given amount → we calculate the change

        If it's a top-up (after NFC insufficient funds), we account for
        the amount already paid in the first transaction.
        """
        # Si c'est un complément, calculer ce qui a déjà été payé
        # If it's a top-up, calculate what was already paid
        montant_deja_paye = 0
        if transaction_precedente:
            montant_deja_paye = (
                transaction_precedente["total"]
                - (transaction_precedente["missing"] * 100)
            )

        somme_donnee_en_centimes = donnees_paiement["given_sum"]
        total_en_centimes = donnees_paiement["total"]

        # La somme est suffisante si :
        # - le caissier n'a rien saisi (= paiement exact, pas de monnaie à rendre)
        # - ou la somme donnée + le premier versement couvre le total
        # The amount is sufficient if:
        # - the cashier entered nothing (= exact payment, no change to give)
        # - or the given sum + first payment covers the total
        somme_est_suffisante = (
            somme_donnee_en_centimes == 0
            or (somme_donnee_en_centimes + montant_deja_paye) >= total_en_centimes
        )

        if somme_est_suffisante:
            # Calculer la monnaie à rendre (en euros)
            # Calculate change to give back (in euros)
            donnees_paiement["give_back"] = 0
            if somme_donnee_en_centimes > total_en_centimes:
                donnees_paiement["give_back"] = (somme_donnee_en_centimes - total_en_centimes) / 100
            donnees_paiement["total"] = total_addition

            context = {
                "currency_data": CURRENCY_DATA,
                "payment": donnees_paiement,
                "monnaie_name": state["place"]["monnaie_name"],
                "moyen_paiement": PAYMENT_METHOD_TRANSLATIONS.get(moyen_paiement_code, ""),
                "deposit_is_present": consigne_dans_panier,
                "total": total_addition,
                "state": state,
                "original_payment": transaction_precedente,
            }
            return render(request, "laboutik/partial/hx_return_payment_success.html", context)

        # Somme insuffisante → ne rien faire (le JS gère la validation côté client)
        # Insufficient amount → do nothing (JS handles client-side validation)
        # NOTE : ce cas ne devrait pas arriver car le JS valide avant d'envoyer.
        # NOTE: this case should not happen because JS validates before sending.
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
        self, request, state, db, donnees_paiement, point_de_vente,
        total_addition, consigne_dans_panier, transaction_precedente,
        moyen_paiement_code,
    ):
        """
        Paiement NFC (cashless) — débite le portefeuille de la carte du client.
        NFC (cashless) payment — debits the client's card wallet.

        Trois issues possibles :
        1. Consigne dans le panier → succès immédiat (remboursement, pas de débit)
        2. Solde suffisant → succès (débit du portefeuille)
        3. Solde insuffisant → on sauvegarde la transaction et on propose un complément
           par espèces, CB ou une autre carte NFC

        Three possible outcomes:
        1. Deposit in the basket → immediate success (refund, no debit)
        2. Sufficient balance → success (wallet debit)
        3. Insufficient balance → we save the transaction and offer a top-up
           via cash, credit card or another NFC card
        """
        # Consigne → pas besoin de vérifier le solde, remboursement direct
        # Deposit → no need to check balance, direct refund
        if consigne_dans_panier:
            context = {
                "currency_data": CURRENCY_DATA,
                "payment": donnees_paiement,
                "monnaie_name": state["place"]["monnaie_name"],
                "moyen_paiement": PAYMENT_METHOD_TRANSLATIONS.get(moyen_paiement_code, ""),
                "deposit_is_present": True,
                "total": total_addition,
                "state": state,
                "original_payment": transaction_precedente,
            }
            return render(request, "laboutik/partial/hx_return_payment_success.html", context)

        # --- Chercher la carte NFC du client ---
        # --- Look up the client's NFC card ---
        tag_id_client = donnees_paiement.get("tag_id", "")
        cartes_trouvees = db.get_by_index("cards", "tag_id", tag_id_client)

        # Carte inconnue → avertissement et retour
        # Unknown card → warning and return
        if not cartes_trouvees:
            context_erreur = {
                "msg_type": "warning",
                "msg_content": _("Carte inconnue !"),
                "selector_bt_retour": "#messages",
            }
            return render(request, "laboutik/partial/hx_messages.html", context_erreur)

        carte_client = cartes_trouvees[0]

        # Solde total = portefeuille principal + portefeuille cadeau
        # Total balance = main wallet + gift wallet
        solde_portefeuille = carte_client["wallets"]
        solde_portefeuille_cadeau = carte_client["wallets_gift"]
        solde_total_carte = solde_portefeuille + solde_portefeuille_cadeau

        # Récupérer les moyens de paiement acceptés par le PV
        # (affiché sur l'écran "fonds insuffisants" pour proposer un complément)
        # Get payment methods accepted by the POS
        # (shown on the "insufficient funds" screen to offer a top-up)
        resultats_pv = db.get_by_index("pvs", "id", donnees_paiement.get("uuid_pv"))
        pv_depuis_db = resultats_pv[0] if resultats_pv else point_de_vente

        context_nfc = {
            "payment": donnees_paiement,
            "monnaie_name": state["place"]["monnaie_name"],
            "moyen_paiement": PAYMENT_METHOD_TRANSLATIONS.get(moyen_paiement_code, ""),
            "state": state,
            "original_payment": transaction_precedente,
            "currency_data": CURRENCY_DATA,
            "wallets": {
                "monnaie": solde_portefeuille,
                "gift_monnaie": solde_portefeuille_cadeau,
            },
            "payments_accepted": {
                "accepte_especes": pv_depuis_db.get("accepte_especes", False),
                "accepte_carte_bancaire": pv_depuis_db.get("accepte_carte_bancaire", False),
                "accepte_cheque": pv_depuis_db.get("accepte_cheque", False),
            },
            "card": carte_client,
        }
        if transaction_precedente:
            context_nfc["original_moyen_paiement"] = PAYMENT_METHOD_TRANSLATIONS.get(
                transaction_precedente.get("moyen_paiement"), "",
            )

        # --- Fonds insuffisants → sauvegarder et proposer un complément ---
        # --- Insufficient funds → save and offer a top-up ---
        if solde_total_carte < total_addition:
            montant_manquant = ((total_addition * 100) - (solde_total_carte * 100)) / 100
            donnees_paiement["missing"] = montant_manquant
            uuid_nouvelle_transaction = db.add("transactions", donnees_paiement)
            context_nfc["uuid_transaction"] = uuid_nouvelle_transaction
            return render(request, "laboutik/partial/hx_funds_insufficient.html", context_nfc)

        # --- Solde suffisant → paiement réussi ---
        # --- Sufficient balance → payment successful ---
        return render(request, "laboutik/partial/hx_return_payment_success.html", context_nfc)

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
