from django.shortcuts import render
from django.http import JsonResponse, HttpResponseNotFound, HttpResponseNotAllowed
from django.conf import settings
from rest_framework import status
from django.utils.translation import gettext as _
from json import dumps
from django_htmx.http import HttpResponseClientRedirect

import sys
from pathlib import Path

# Ajoutez le répertoire utils au chemin d'importation
# Path(__file__) = /DjangoFiles/laboutik/views.py
sys.path.append(str(Path(__file__).resolve().parent / "utils"))

# data mocker - dev
import mockData

import method

data_pvs = mockData.get_data_pvs()

state = {
    "version": "0.9.11",
    "demo": {
        "active": settings.DEMO,
        "tags_id": [
            {"tag_id": settings.DEMO_TAGID_CM, "name": _("Carte primaire")},
            {"tag_id": settings.DEMO_TAGID_CLIENT1, "name": _("Carte client 1")},
            {"tag_id": settings.DEMO_TAGID_CLIENT2, "name": _("Carte client 2")},
            {"tag_id": settings.DEMO_TAGID_CLIENT3, "name": _("Carte client 3")},
            {"tag_id": settings.DEMO_TAGID_UNKNOWN, "name": _("Carte client inconnu")},
        ],
    },
}


def login_hardware(request):
    context = {"state": state, "stateJson": dumps(state)}
    # dev
    devLoginOk = 1

    if request.method == "POST":
        if devLoginOk == 1:
            return HttpResponseClientRedirect("ask_primary_card")

        if devLoginOk == 0:
            context = {"error": _("Utilisateur non actif. Relancez l'appairage.")}
            return render(request, "components/new-hardware-error.html", context)

        # DEBUG = AttributeError: module 'rest_framework.status' has no attribute 'HTTP_400_UNAUTHORIZED'
        if devLoginOk == 2:
            context = {"error": _("*** login_hardware_validator.errors ***")}
            return render(request, "components/hardware-login-error.html", context)

    if request.method == "GET":
        activation = request.GET.get("activation")
        context["activation"] = activation

    return render(request, "views/login_hardware.html", context)


def new_hardware(request):
    # dev
    devHardwareOk = True

    # hardware active
    if devHardwareOk == True:
        # Le code pin a été validé, on renvoie vers la page de login
        return HttpResponseClientRedirect("login_hardware?activation=1")

    # error
    if devHardwareOk == False:
        context = {
            "error": _(
                "Appareil déja en cours d'utilisation. Désactivez le d'abord pour un nouvel appairage."
            )
        }
        return render(request, "components/new-hardware-error.html", context)


def ask_primary_card(request):
    # dev
    # state['demo']['active'] = False

    context = {"state": state, "stateJson": dumps(state)}

    if request.method == "POST":
        tag_id_cm = request.POST.get("tag-id-cm").upper()
        print(f"ask_primary_card, tag_id_cm = {tag_id_cm}")

        # dev
        carte_perdu = False
        testCard = mockData.get_card_from_tagid(tag_id_cm)
        print(f"laboutik - DEV | testCard = {testCard}")

        # carte primaire
        if testCard["type_card"] == "primary_card" and testCard["tag_id"] == "A49E8E2A":
            print("laboutik - DEV | c'est une carte primaire")
            # carte perdue
            if carte_perdu:
                context = {"msg": _("Carte perdue ? On passe en non primaire")}
                return render(request, "components/primary_card_message.html", context)
            else:
                # carte primaire ok
                uuid_pv = testCard["pvs_list"][0]["uuid"]
                print(f"laboutik - DEV | uuid pv = {uuid_pv}")
                return HttpResponseClientRedirect(
                    "pv_route?uuid_pv=" + uuid_pv + "&tag_id_cm=" + tag_id_cm
                )

        # carte cliente
        if testCard["type_card"] == "client_card":
            print("laboutik - DEV | c'est une carte client")
            context = {"msg": _("Carte non primaire")}
            return render(request, "components/primary_card_message.html", context)

        # carte inconnue
        if testCard["type_card"] == "unknown":
            context = {"msg": _("Carte inconnue")}
            return render(request, "components/primary_card_message.html", context)

    return render(request, "views/ask_primary_card.html", context)

def pv_route(request):
    # pour un mode restaurant (non service direct)
    try:
        id_table = int(request.GET.get("id_table"))
    except:
        id_table = None

    # force le service direct en mode restaurant
    force_service_direct = (
        True if request.GET.get("force_service_direct") == "true" else None
    )

    # mode restaurant forcer en service direct
    restaurant_service_direct = request.GET.get("restaurant_service_direct")
    uuid_pv = request.GET.get("uuid_pv")
    tag_id_cm = request.GET.get("tag_id_cm")
    pv = mockData.get_pv_from_uuid(uuid_pv, data_pvs)
    card = mockData.get_card_from_tagid(tag_id_cm)
    # restaurant par défaut
    title = _("Choisir une table")
    template = "tables.html"

    # service directe
    if pv["service_direct"] == True or force_service_direct == True:
        title = _("Service direct")
        template = "common_user_interface.html"

    # commandes table
    if id_table != None:
        table_name = mockData.get_table_by_id(id_table)["name"]
        print(f"table_name = {table_name}")
        title = _("Commande table ") + table_name
        template = "common_user_interface.html"

    # kiosque
    if pv["comportement"] == "K":
        template = "kiosk.html"

    print(f"laboutik - DEV | template = {template}")

    state["comportement"] = pv["comportement"]
    state["afficher_les_prix"] = pv["afficher_les_prix"]
    state["accepte_especes"] = pv["accepte_especes"]
    state["accepte_carte_bancaire"] = pv["accepte_carte_bancaire"]
    state["accepte_cheque"] = pv["accepte_cheque"]
    state["accepte_commandes"] = pv["accepte_commandes"]
    state["service_direct"] = pv["service_direct"]
    state["monnaie_principale_name"] = "TestCoin"
    state["passageModeGerant"] = True
    state["mode_gerant"] = card['mode_gerant']
    # triage par poid_liste
    card["pvs_list"] = sorted(card["pvs_list"], key=lambda x: x["poid_liste"])

    context = {
        "state": state,
        "stateJson": dumps(state),
        "pv": pv,
        "card": card,
        "categories": mockData.filter_categories(pv),
        "categoriy_angry": mockData.categoriy_angry,
        "tables": mockData.tables,
        "table_status_colors": {"S": "--orange01", "O": "--rouge01", "L": "--vert02"},
        "title": title,
        "currency_data": {"cc": "EUR", "symbol": "€", "name": "European Euro"},
        "uuidArticlePaiementFractionne": "42ffe511-d880-4964-9b96-0981a9fe4071",
        "id_table": id_table,
    }
    return render(request, "views/" + template, context)

def check_card(request):
	tag_id_request = request.data.get('tag_id_client').upper()
	card = mockData.get_card_from_tagid(tag_id_request)
	background = '--warning'

	if card['type_card'] == 'unknown':
		background = '--rouge06'
		error_msg =  _('Carte inconnue')

	context = {
		"card": card
	}
	return render(request, "components/check_card.html", context)


def display_type_payment(request):
	dataPost = request.POST
	tag_id_cm = dataPost.get("tag_id_cm")
	uuid_pv = dataPost.get("uuid_pv")
	id_table = dataPost.get("id_table")

	# récupère uniquement les uuid articles
	uuids = method.post_filter(request.POST)

	if len(uuids) > 0:
		# obtenir le point de vente en fonction de son uuid
		pv = mockData.get_pv_from_uuid(uuid_pv, data_pvs)

		# retourne les moyens de paiement nécessaires et filtrés par moyens de paiement acceptés
		moyens_paiement = method.selection_moyens_paiement(pv, uuids, request.POST)

		# import ipdb; ipdb.set_trace()
		# calcul du total de l'addition
		total = method.calcul_total_addition(pv, uuids, request.POST)

		context = {
			"moyens_paiement": moyens_paiement,
			"currency_data": {"cc": "EUR", "symbol": "€", "name": "European Euro"},
			"total": total,
			"selector_bt_retour": "#messages"
		}

		return render(request, "components/moyens_paiement.html", context)

	else:
		# aucun article
		context = {
			'msg_type': 'info',
			'msg_content': _("Aucun article n'a été selectioné")
		}
		return render(request, "components/messages.html", context)

def read_nfc(request):
	context = {
		'message': _("Attente lecture carte")
	}
	return render(request, "components/read_nfc.html", context)

def confirm_payment(request):
	payment_method = request.GET.get("method")
	payments = {
		'nfc': _('cashless'),
		'espece': _('espèce'),
		'carte_bancaire': _('carte bancaire'),
		'CH': _('chèque')
	}
	context = {
		'method': payment_method,
		'payment_method': payments[payment_method],
		'selector_bt_retour': '#confirm'
	}
	return render(request, "components/confirm_payment.html", context)

def payment(request):
	# msg_type = success, info, error, warning

	# # attention pas de test si method = post
	# # dev
	paiement_ok = False

	if paiement_ok:
		context = {
			'msg_type': 'success',
			'msg_content': _('Paiement ok')
		}
	if paiement_ok == False:
		context = {
			'msg_type': "warning",
			'msg_content': "Il y a une erreur !",
			'selector_bt_retour': '#messages'
		}

	return render(request, "components/messages.html", context)
