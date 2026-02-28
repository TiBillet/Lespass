# laboutik/views.py
# ViewSets DRF pour l'interface de caisse LaBoutik (POS tactile).
# DRF ViewSets for the LaBoutik cash register interface (touch POS).
#
# Authentification : clé API LaBoutik (Discovery / PIN pairing) ou session admin tenant.
# Authentication: LaBoutik API key (Discovery / PIN pairing) or tenant admin session.
#
# IMPORTANT : toutes les données sont mockées (JSON fichier).
# Les vrais modèles Django seront créés plus tard.
# IMPORTANT: all data is mocked (JSON file).
# Real Django models will be created later.

import os
from json import dumps

from django.conf import settings
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _
from django_htmx.http import HttpResponseClientRedirect
from rest_framework import viewsets
from rest_framework.decorators import action

from BaseBillet.permissions import HasLaBoutikAccess
from laboutik.utils import mockData
from laboutik.utils import method as payment_method


# --------------------------------------------------------------------------- #
#  Constantes mock — seront remplacées par de vrais modèles plus tard         #
#  Mock constants — will be replaced by real Django models later               #
# --------------------------------------------------------------------------- #

# Chemin vers la base de données JSON mock
# Path to the mock JSON database
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


# --------------------------------------------------------------------------- #
#  Fonctions utilitaires — construire l'état et charger les données mock      #
#  Utility functions — build state and load mock data                         #
# --------------------------------------------------------------------------- #

def _construire_state():
    """
    Construit le dictionnaire "state" à chaque requête.
    Builds the "state" dictionary on each request.

    Pas de variable globale mutable : on reconstruit à chaque appel
    pour éviter les effets de bord entre requêtes concurrentes.
    No mutable global: we rebuild on each call
    to avoid side effects between concurrent requests.
    """
    return {
        "version": "0.9.11",
        "place": {"name": "lieu de test", "monnaie_name": "lémien"},
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


def _charger_mock_db():
    """
    Charge la base de données JSON mock (relecture à chaque requête).
    Loads the mock JSON database (re-read on each request).
    """
    return mockData.mockDb(MOCK_DB_PATH)


def _charger_points_de_vente():
    """
    Charge les points de vente mock avec leurs articles corrigés.
    Loads mock points of sale with their corrected articles.
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
        Reçoit le tag NFC scanné, vérifie le type de carte, et redirige.
        Receives the scanned NFC tag, checks the card type, and redirects.

        - Carte primaire → redirige vers le point de vente / redirects to POS
        - Carte cliente → message "carte non primaire" / "not a primary card" message
        - Carte inconnue → message "carte inconnue" / "unknown card" message
        """
        db = _charger_mock_db()
        tag_id_carte_manager = request.POST.get("tag_id", "").upper()

        # Chercher la carte dans la base mock par son tag NFC
        # Look up the card in the mock database by its NFC tag
        cartes_trouvees = db.get_by_index("cards", "tag_id", tag_id_carte_manager)
        if not cartes_trouvees:
            carte = {"type_card": "unknown"}
        else:
            carte = cartes_trouvees[0]

        # Carte primaire (responsable de caisse) → rediriger vers le point de vente
        # Primary card (cash register manager) → redirect to the point of sale
        type_carte = carte.get("type_card")
        if type_carte == "primary_card":
            uuid_premier_pv = carte["pvs_list"][0]["uuid"]
            url_point_de_vente = reverse("laboutik-caisse-point_de_vente")
            url_avec_params = f"{url_point_de_vente}?uuid_pv={uuid_premier_pv}&tag_id_cm={tag_id_carte_manager}"
            return HttpResponseClientRedirect(url_avec_params)

        # Carte cliente — pas autorisée à ouvrir la caisse
        # Client card — not authorized to open the register
        if type_carte == "client_card":
            return render(request, "laboutik/partial/hx_primary_card_message.html", {
                "msg": _("Carte non primaire"),
            })

        # Carte inconnue — tag NFC non reconnu
        # Unknown card — NFC tag not recognized
        return render(request, "laboutik/partial/hx_primary_card_message.html", {
            "msg": _("Carte inconnue"),
        })

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
        state = _construire_state()
        db = _charger_mock_db()
        tous_les_points_de_vente = _charger_points_de_vente()

        uuid_pv = request.GET.get("uuid_pv")
        tag_id_carte_manager = request.GET.get("tag_id_cm")

        # Récupérer l'ID de table (mode restaurant uniquement)
        # Get the table ID (restaurant mode only)
        try:
            id_table = int(request.GET.get("id_table"))
        except (TypeError, ValueError):
            id_table = None

        # Le paramètre force_service_direct permet de court-circuiter le mode tables
        # The force_service_direct parameter bypasses table mode
        force_service_direct = request.GET.get("force_service_direct") == "true"

        point_de_vente = mockData.get_pv_from_uuid(uuid_pv, tous_les_points_de_vente)
        cartes_trouvees = db.get_by_index("cards", "tag_id", tag_id_carte_manager)
        carte_manager = cartes_trouvees[0] if cartes_trouvees else {}

        # --- Choisir le template selon le mode du point de vente ---
        # --- Choose the template based on the point of sale mode ---
        #
        # Le champ "comportement" du point de vente détermine son mode :
        # The "comportement" field of the point of sale determines its mode:
        #   "C" = Cashless (vente directe / direct sale)
        #   "K" = Kiosk (borne libre-service / self-service terminal)
        #   autre = Restaurant (avec tables / with tables)

        # Par défaut : mode restaurant → afficher le choix des tables
        # Default: restaurant mode → show table selection
        titre_page = _("Choisir une table")
        template_name = "laboutik/views/tables.html"

        # Service direct (pas de tables) → interface de vente directe
        # Direct service (no tables) → direct sales interface
        if point_de_vente["service_direct"] or force_service_direct:
            titre_page = _("Service direct")
            template_name = "laboutik/views/common_user_interface.html"

        # Une table spécifique est sélectionnée → interface de commande
        # A specific table is selected → order interface
        if id_table is not None:
            nom_table = mockData.get_table_by_id(id_table)["name"]
            titre_page = _("Commande table ") + nom_table
            template_name = "laboutik/views/common_user_interface.html"

        # Mode kiosk (borne libre-service) → template spécifique
        # Kiosk mode (self-service terminal) → specific template
        comportement_du_pv = point_de_vente["comportement"]
        if comportement_du_pv == "K":
            template_name = "laboutik/views/kiosk.html"

        # Enrichir le state avec les propriétés du point de vente.
        # Le JS côté client lit "state" (via stateJson) pour piloter l'interface :
        # afficher/masquer les boutons de paiement, activer le mode gérant, etc.
        # Enrich state with point of sale properties.
        # Client-side JS reads "state" (via stateJson) to drive the interface:
        # show/hide payment buttons, enable manager mode, etc.
        state["comportement"] = comportement_du_pv
        state["afficher_les_prix"] = point_de_vente["afficher_les_prix"]
        state["accepte_especes"] = point_de_vente["accepte_especes"]
        state["accepte_carte_bancaire"] = point_de_vente["accepte_carte_bancaire"]
        state["accepte_cheque"] = point_de_vente["accepte_cheque"]
        state["accepte_commandes"] = point_de_vente["accepte_commandes"]
        state["service_direct"] = point_de_vente["service_direct"]
        state["monnaie_principale_name"] = "TestCoin"
        # passageModeGerant : autorise le caissier à basculer en mode gérant (bouton visible)
        # passageModeGerant: allows the cashier to switch to manager mode (button visible)
        state["passageModeGerant"] = True
        state["mode_gerant"] = carte_manager.get("mode_gerant", False)

        # Trier les points de vente par poids d'affichage
        # Sort points of sale by display weight
        carte_manager["pvs_list"] = sorted(
            carte_manager.get("pvs_list", []),
            key=lambda pv: pv["poid_liste"],
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

        context = {
            "hostname_client": "mock host name from device login",
            "state": state,
            "stateJson": dumps(state),
            # "pv" et "card" : noms courts imposés par les templates cotton et JS existants
            # "pv" and "card": short names required by existing cotton templates and JS
            "pv": point_de_vente,
            "card": carte_manager,
            "categories": mockData.filter_categories(point_de_vente),
            "categoriy_angry": mockData.categoriy_angry,
            "tables": mockData.tables,
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
        return render(request, "laboutik/partial/hx_messages.html", context_erreur)

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
