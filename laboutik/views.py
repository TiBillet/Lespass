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

# dev
import mockData

# utils
import methods

state =  {
	'version': '0.9.11',
	'demo': {
		'active': settings.DEMO,
		'tags_id': [
    	{'tag_id': settings.DEMO_TAGID_CM, 'name': _("Carte primaire")},
			{'tag_id': settings.DEMO_TAGID_CLIENT1, 'name': _("Carte client 1")},
			{'tag_id': settings.DEMO_TAGID_CLIENT2, 'name': _("Carte client 2")},
			{'tag_id': settings.DEMO_TAGID_CLIENT3, 'name': _("Carte client 3")},
			{'tag_id': settings.DEMO_TAGID_UNKNOWN, 'name': _("Carte client inconnu")}
		]
	}
}

def login_hardware(request):
	context = {
		'state': state,
		'stateJson': dumps(state)
  }
	# dev
	devLoginOk = 1
	
	if request.method == 'POST':
		if devLoginOk == 1:
			return HttpResponseClientRedirect('ask_primary_card')

		if devLoginOk == 0:
			context = {
				'error': _("Utilisateur non actif. Relancez l'appairage.")
			}
			return render(request, "components/new-hardware-error.html", context)

		# DEBUG = AttributeError: module 'rest_framework.status' has no attribute 'HTTP_400_UNAUTHORIZED'  
		if devLoginOk == 2:
			context = {
				'error': _("*** login_hardware_validator.errors ***")
			}
			return render(request, "components/hardware-login-error.html", context)

	if request.method == 'GET':
		activation = request.GET.get('activation')
		context['activation'] = activation

	return render(request, "views/login_hardware.html", context)


def new_hardware(request):
	# dev
	devHardwareOk = True

	# hardware active
	if devHardwareOk == True:
		# Le code pin a été validé, on renvoie vers la page de login
		return HttpResponseClientRedirect('login_hardware?activation=1')

	# error
	if devHardwareOk == False:
		context = {
			'error': _("Appareil déja en cours d'utilisation. Désactivez le d'abord pour un nouvel appairage.")
		}
		return render(request, "components/new-hardware-error.html", context)

def ask_primary_card(request):
	# dev
	state['demo']['active'] = False
	
	context = {
		'state': state,
    'stateJson': dumps(state)
  }

	if request.method == 'POST':
		tag_id_cm = request.POST.get('tag-id-cm').upper()
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
				context = {
					'msg': _("Carte perdue ? On passe en non primaire")
				}
				return render(request, "components/primary_card_message.html", context)
			else:
				uuid_pv = testCard['pvs_list'][0]['uuid']
				print(f"laboutik - DEV | uuid pv = {uuid_pv}")
				return HttpResponseClientRedirect('pv_route?uuid_pv=' + uuid_pv + '&tag_id_cm=' + tag_id_cm)

		# carte cliente
		if testCard["type_card"] == "client_card":
			print("laboutik - DEV | c'est une carte client")
			context = {
				'msg': _("Carte non primaire")
			}
			return render(request, "components/primary_card_message.html", context)

		# carte inconnue
		if testCard["type_card"] == "unknown":
			context = {
				'msg':  _("Carte inconnue")
			}
			return render(request, "components/primary_card_message.html", context)


	return render(request, "views/ask_primary_card.html", context)

def main_menu(request):
	tag_id_cm = request.GET.get('tag_id_cm')
	card = mockData.get_card_from_tagid(tag_id_cm)
	context = {
		'card': card,
	}
	return render(request, "components/main_menu.html", context)

def pvs_menu(request):
	tag_id_cm = request.GET.get('tag_id_cm')
	card = mockData.get_card_from_tagid(tag_id_cm)
	context = {
		'card': card,
	}
	return render(request, "components/pvs_menu.html", context)

def show_pv(request):
	uuid_pv = request.GET.get('uuid_pv')
	pv = mockData.get_pv_from_uuid(uuid_pv)
	context = {
		'pv': pv
	}
	return render(request, "components/show_pv.html", context)


def pv_route(request):
	id_tables = request.GET.get('id_tables')
	uuid_pv = request.GET.get('uuid_pv')
	tag_id_cm = request.GET.get('tag_id_cm')
	print(f"laboutik - DEV | uuid_pv = {uuid_pv}  --  tag_id_cm = {tag_id_cm}  --  id_tables = {id_tables}")
	pv = mockData.get_pv_from_uuid(uuid_pv)
	card = mockData.get_card_from_tagid(tag_id_cm)
	# restaurent par défaut
	template = 'tables.html'
	
	# service directe
	if pv['service_direct'] == True:
		template = 'common_interface.html'

	# kiosque
	if pv['comportement'] == 'K':
		template = 'kiosk.html'


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
	state["modeGerant"] = False
	state["currencyData"] = {"cc": "EUR", "symbol": "€", "name": "European Euro"}

	context = {
		'state': state,
		'stateJson': dumps(state),
		'pv': pv,
		'card': card,
		'categories': methods.filter_categories(pv)
	}
	return render(request, "views/" + template, context)