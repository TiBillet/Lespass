# laboutik/views.py — ViewSets DRF pour la caisse LaBoutik
# Auth : LaBoutikAPIKey via Discovery (PIN pairing)
# Données : mock (pas de modèles Django pour l'instant)

import os
from json import dumps

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.template import Template, RequestContext
from django.utils.translation import gettext as _
from django_htmx.http import HttpResponseClientRedirect
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from BaseBillet.permissions import HasLaBoutikAccess
from laboutik.utils import mockData
from laboutik.utils import method


# --------------------------------------------------------------------------- #
#  Données mock — seront remplacées par de vrais modèles plus tard            #
# --------------------------------------------------------------------------- #

MOCK_DB_PATH = os.path.join(os.path.dirname(__file__), "utils", "mockDb.json")

CURRENCY_DATA = {"cc": "EUR", "symbol": "€", "name": "European Euro"}

PAYMENTS_TRANSLATION = {
    "nfc": _("cashless"),
    "espece": _("espèce"),
    "carte_bancaire": _("carte bancaire"),
    "CH": _("chèque"),
    "gift": _("cadeau"),
    "": _("inconnu"),
}

UUID_ARTICLE_CONSIGNE = "8f08b90d-d3f0-49da-9dbd-8be795f689ef"


def _construire_state():
    """Construit le dict state à chaque requête (pas de global mutable)."""
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


def _get_db():
    """Retourne une instance mockDb (relecture du JSON à chaque requête)."""
    return mockData.mockDb(MOCK_DB_PATH)


def _get_data_pvs():
    """Retourne les points de vente mock avec articles corrigés."""
    return mockData.get_data_pvs()


# --------------------------------------------------------------------------- #
#  CaisseViewSet — pages principales                                          #
# --------------------------------------------------------------------------- #

class CaisseViewSet(viewsets.ViewSet):
    """Pages principales de la caisse : carte primaire, point de vente."""
    permission_classes = [HasLaBoutikAccess]

    def list(self, request):
        """GET /laboutik/caisse/ → page d'attente carte primaire."""
        state = _construire_state()
        context = {
            "state": state,
            "stateJson": dumps(state),
            "method": request.method,
        }
        return render(request, "laboutik/views/ask_primary_card.html", context)

    @action(detail=False, methods=["post"], url_path="carte_primaire", url_name="carte_primaire")
    def carte_primaire(self, request):
        """POST /laboutik/caisse/carte_primaire/ → valide la carte, redirige vers le PV."""
        state = _construire_state()
        db = _get_db()
        tag_id_cm = request.POST.get("tag_id", "").upper()

        # Chercher la carte dans le mock DB
        card_list = db.get_by_index("cards", "tag_id", tag_id_cm)
        if not card_list:
            card = {"type_card": "unknown"}
        else:
            card = card_list[0]

        # Carte primaire — rediriger vers le point de vente
        if card.get("type_card") == "primary_card":
            from django.urls import reverse
            uuid_pv = card["pvs_list"][0]["uuid"]
            base_url = reverse("laboutik-caisse-point_de_vente")
            redirect_url = f"{base_url}?uuid_pv={uuid_pv}&tag_id_cm={tag_id_cm}"
            return HttpResponseClientRedirect(redirect_url)

        # Carte cliente
        if card.get("type_card") == "client_card":
            return render(request, "laboutik/partial/hx_primary_card_message.html", {
                "msg": _("Carte non primaire"),
            })

        # Carte inconnue
        return render(request, "laboutik/partial/hx_primary_card_message.html", {
            "msg": _("Carte inconnue"),
        })

    @action(detail=False, methods=["get"], url_path="point_de_vente", url_name="point_de_vente")
    def point_de_vente(self, request):
        """GET /laboutik/caisse/point_de_vente/ → interface POS."""
        state = _construire_state()
        db = _get_db()
        data_pvs = _get_data_pvs()

        uuid_pv = request.GET.get("uuid_pv")
        tag_id_cm = request.GET.get("tag_id_cm")

        # Table (mode restaurant)
        try:
            id_table = int(request.GET.get("id_table"))
        except (TypeError, ValueError):
            id_table = None

        force_service_direct = request.GET.get("force_service_direct") == "true"

        pv = mockData.get_pv_from_uuid(uuid_pv, data_pvs)
        card_list = db.get_by_index("cards", "tag_id", tag_id_cm)
        card = card_list[0] if card_list else {}

        # Choisir le template selon le mode
        title = _("Choisir une table")
        template = "laboutik/views/tables.html"

        if pv["service_direct"] or force_service_direct:
            title = _("Service direct")
            template = "laboutik/views/common_user_interface.html"

        if id_table is not None:
            table_name = mockData.get_table_by_id(id_table)["name"]
            title = _("Commande table ") + table_name
            template = "laboutik/views/common_user_interface.html"

        if pv["comportement"] == "K":
            template = "laboutik/views/kiosk.html"

        # Enrichir state avec les propriétés du PV
        state["comportement"] = pv["comportement"]
        state["afficher_les_prix"] = pv["afficher_les_prix"]
        state["accepte_especes"] = pv["accepte_especes"]
        state["accepte_carte_bancaire"] = pv["accepte_carte_bancaire"]
        state["accepte_cheque"] = pv["accepte_cheque"]
        state["accepte_commandes"] = pv["accepte_commandes"]
        state["service_direct"] = pv["service_direct"]
        state["monnaie_principale_name"] = "TestCoin"
        state["passageModeGerant"] = True
        state["mode_gerant"] = card.get("mode_gerant", False)

        # Trier les PV par poid_liste
        card["pvs_list"] = sorted(card.get("pvs_list", []), key=lambda x: x["poid_liste"])

        context = {
            "hostname_client": "mock host name from device login",
            "state": state,
            "stateJson": dumps(state),
            "pv": pv,
            "card": card,
            "categories": mockData.filter_categories(pv),
            "categoriy_angry": mockData.categoriy_angry,
            "tables": mockData.tables,
            "table_status_colors": {"S": "--orange01", "O": "--rouge01", "L": "--vert02"},
            "title": title,
            "currency_data": CURRENCY_DATA,
            "uuidArticlePaiementFractionne": "42ffe511-d880-4964-9b96-0981a9fe4071",
            "id_table": id_table,
        }
        return render(request, template, context)


# --------------------------------------------------------------------------- #
#  PaiementViewSet — HTMX partials du flux de paiement                        #
# --------------------------------------------------------------------------- #

class PaiementViewSet(viewsets.ViewSet):
    """Partials HTMX pour le flux de paiement de la caisse."""
    permission_classes = [HasLaBoutikAccess]

    @action(detail=False, methods=["post"], url_path="moyens_paiement", url_name="moyens_paiement")
    def moyens_paiement(self, request):
        """POST → affiche les types de paiement disponibles."""
        state = _construire_state()
        data_pvs = _get_data_pvs()

        uuid_pv = request.POST.get("uuid_pv")
        uuids = method.post_filter(request.POST)
        pv = mockData.get_pv_from_uuid(uuid_pv, data_pvs)

        moyens_paiement = method.selection_moyens_paiement(pv, uuids, request.POST)
        total = method.calcul_total_addition(pv, uuids, request.POST)

        # Mock
        mode_gerant = False
        deposit_is_present = UUID_ARTICLE_CONSIGNE in uuids
        if deposit_is_present:
            total = abs(total)

        context = {
            "state": state,
            "moyens_paiement": moyens_paiement,
            "currency_data": CURRENCY_DATA,
            "total": total,
            "mode_gerant": mode_gerant,
            "deposit_is_present": deposit_is_present,
            "comportement": pv["comportement"],
        }
        return render(request, "laboutik/partial/hx_display_type_payment.html", context)

    @action(detail=False, methods=["get"], url_path="confirmer", url_name="confirmer")
    def confirmer(self, request):
        """GET → confirmation avant paiement."""
        payment_method = request.GET.get("method")
        total = request.GET.get("total")
        uuid_transaction = request.GET.get("uuid_transaction", "")

        context = {
            "method": payment_method,
            "total": total,
            "payment_translation": PAYMENTS_TRANSLATION.get(payment_method, ""),
            "uuid_transaction": uuid_transaction,
            "currency_data": CURRENCY_DATA,
        }
        return render(request, "laboutik/partial/hx_confirm_payment.html", context)

    @action(detail=False, methods=["post"], url_path="payer", url_name="payer")
    def payer(self, request):
        """POST → exécute le paiement (mock)."""
        state = _construire_state()
        db = _get_db()
        data_pvs = _get_data_pvs()

        uuids = method.post_filter(request.POST)
        payment = request.POST.dict()

        payment["total"] = int(payment.get("total", 0))
        payment["given_sum"] = 0 if payment.get("given_sum") == "" else int(payment.get("given_sum", 0))
        payment["missing"] = 0

        deposit_is_present = UUID_ARTICLE_CONSIGNE in uuids
        pv = mockData.get_pv_from_uuid(payment.get("uuid_pv"), data_pvs)
        total = method.calcul_total_addition(pv, uuids, request.POST)
        if deposit_is_present:
            total = abs(total)

        # Récupère la transaction originale (fonds insuffisants)
        original_payment = None
        if payment.get("uuid_transaction", "") != "":
            transaction_search = db.get_by_index("transactions", "id", payment["uuid_transaction"])
            if transaction_search and len(transaction_search) == 1:
                original_payment = transaction_search[0]

        context = {
            "currency_data": CURRENCY_DATA,
            "payment": payment,
            "monnaie_name": state["place"]["monnaie_name"],
            "moyen_paiement": PAYMENTS_TRANSLATION.get(payment.get("moyen_paiement"), ""),
            "deposit_is_present": deposit_is_present,
            "total": total,
            "state": state,
            "original_payment": original_payment,
        }

        moyen = payment.get("moyen_paiement", "")

        # Paiement CB ou chèque
        if moyen in ("carte_bancaire", "CH"):
            payment["total"] = payment["total"] / 100
            return render(request, "laboutik/partial/hx_return_payment_success.html", context)

        # Paiement espèce
        if moyen == "espece":
            bring_first_transaction = 0
            if original_payment:
                bring_first_transaction = original_payment["total"] - (original_payment["missing"] * 100)

            if payment["given_sum"] == 0 or (payment["given_sum"] + bring_first_transaction) >= payment["total"]:
                payment["give_back"] = 0
                if payment["given_sum"] > payment["total"]:
                    payment["give_back"] = (payment["given_sum"] - payment["total"]) / 100
                payment["total"] = total
                return render(request, "laboutik/partial/hx_return_payment_success.html", context)

        # Paiement NFC / cashless
        if moyen == "nfc":
            if deposit_is_present:
                return render(request, "laboutik/partial/hx_return_payment_success.html", context)

            card_list = db.get_by_index("cards", "tag_id", payment.get("tag_id", ""))

            # Carte inconnue
            if not card_list:
                context = {
                    "msg_type": "warning",
                    "msg_content": _("Carte inconnue !"),
                    "selector_bt_retour": "#messages",
                }
                return render(request, "laboutik/partial/hx_messages.html", context)

            card = card_list[0]
            total_wallets = card["wallets"] + card["wallets_gift"]

            pv_db = db.get_by_index("pvs", "id", payment.get("uuid_pv"))
            pv_from_db = pv_db[0] if pv_db else pv

            context = {
                "payment": payment,
                "monnaie_name": state["place"]["monnaie_name"],
                "moyen_paiement": PAYMENTS_TRANSLATION.get(moyen, ""),
                "state": state,
                "original_payment": original_payment,
                "currency_data": CURRENCY_DATA,
                "wallets": {
                    "monnaie": card["wallets"],
                    "gift_monnaie": card["wallets_gift"],
                },
                "payments_accepted": {
                    "accepte_especes": pv_from_db.get("accepte_especes", False),
                    "accepte_carte_bancaire": pv_from_db.get("accepte_carte_bancaire", False),
                    "accepte_cheque": pv_from_db.get("accepte_cheque", False),
                },
                "card": card,
            }
            if original_payment:
                context["original_moyen_paiement"] = PAYMENTS_TRANSLATION.get(
                    original_payment.get("moyen_paiement"), ""
                )

            # Fonds insuffisants
            if total_wallets < total:
                payment["missing"] = ((total * 100) - (total_wallets * 100)) / 100
                uuid_transaction = db.add("transactions", payment)
                context["uuid_transaction"] = uuid_transaction
                return render(request, "laboutik/partial/hx_funds_insufficient.html", context)
            else:
                return render(request, "laboutik/partial/hx_return_payment_success.html", context)

        # Erreur par défaut
        context = {
            "msg_type": "warning",
            "msg_content": "Il y a une erreur !",
            "selector_bt_retour": "#messages",
        }
        return render(request, "laboutik/partial/hx_messages.html", context)

    @action(detail=False, methods=["get"], url_path="lire_nfc", url_name="lire_nfc")
    def lire_nfc(self, request):
        """GET → partial attente lecture NFC."""
        return render(request, "laboutik/partial/hx_read_nfc.html", {})

    @action(detail=False, methods=["get"], url_path="verifier_carte", url_name="verifier_carte")
    def verifier_carte(self, request):
        """GET → partial vérification carte."""
        return render(request, "laboutik/partial/hx_check_card.html", {})

    @action(detail=False, methods=["post"], url_path="retour_carte", url_name="retour_carte")
    def retour_carte(self, request):
        """POST → feedback carte NFC."""
        state = _construire_state()
        db = _get_db()
        tag_id = request.POST.get("tag_id", "").upper()
        background = "--success"

        card_list = db.get_by_index("cards", "tag_id", tag_id)
        if not card_list:
            card = {"type_card": "unknown", "wallets": 0, "wallets_gift": 0, "email": None}
            background = "--error"
        else:
            card = card_list[0]
            if card.get("email") is None:
                background = "--warning"

        context = {
            "card": card,
            "total_monnaie": card["wallets"] + card["wallets_gift"],
            "tag_id": tag_id,
            "background": background,
            "state": state,
        }
        return render(request, "laboutik/partial/hx_card_feedback.html", context)
