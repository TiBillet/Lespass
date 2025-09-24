from django.shortcuts import render
from django.http import JsonResponse, HttpResponseNotFound, HttpResponseNotAllowed
from django.conf import settings
from rest_framework import status
from django.utils.translation import gettext as _
from json import dumps

import sys
from pathlib import Path

# Ajoutez le répertoire utils au chemin d'importation
# Path(__file__) = /DjangoFiles/laboutik/views.py
sys.path.append(str(Path(__file__).resolve().parent / "utils"))

import mockData

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
			return JsonResponse({"user_activation": "true"}, status=status.HTTP_200_OK)

		if devLoginOk == 0:
			return JsonResponse({"msg": _("Utilisateur non actif. Relancez l'appairage.")},status=status.HTTP_401_UNAUTHORIZED)

		# DEBUG = AttributeError: module 'rest_framework.status' has no attribute 'HTTP_400_UNAUTHORIZED'  
		if devLoginOk == 2:
			return JsonResponse({"msg": _("*** login_hardware_validator.errors ***")},status=status.HTTP_400_UNAUTHORIZED)

	return render(request, "views/login_hardware.html", context)

def new_hardware(request):
	# dev
	devHardwareOk = 1

	if devHardwareOk == 1:
		print(f"username = {request.POST['username']}")
		# Le code pin a été validé, on renvoie vers la page de login
		return JsonResponse({"msg": "ok"}, status=status.HTTP_201_CREATED)

	if devHardwareOk == 0:
		return JsonResponse({'msg': _("Appareil déja en cours d'utilisation. Désactivez le d'abord pour un nouvel appairage.")},status=status.HTTP_400_BAD_REQUEST)

def ask_primary_card(request):
	state['demo']['active'] = False
	context = {
		'state': state,
    'stateJson': dumps(state)
  }

	if request.method == 'POST':
		if request.POST.get('type-action') == 'valider_carte_maitresse':
			tag_id_cm = request.POST.get('tag-id-cm').upper()
			print(f"ask_primary_card, tag_id_cm = {tag_id_cm}")
			
			# dev
			token = 'jkjhhjjjjkmlkmlkmlkmlk'
			carte_perdu = False
			testCard = mockData.get_card_from_tagid(tag_id_cm)
			print(f"laboutik - DEV | testCard = {testCard}")

			# carte primaire
			if testCard["type_card"] == "primary_card" and testCard["tag_id"] == "A49E8E2A":
				print("laboutik - DEV | c'est une carte primaire")
				# carte perdue
				if carte_perdu:
					return JsonResponse({"msg": _("Carte perdue ? On passe en non primaire")},status=status.HTTP_400_BAD_REQUEST)
				else:
					# trouver uuid pv 0
					uuid_pv = testCard['pvs_list'][0]['uuid']
					print(f"laboutik - DEV | uuid pv = {uuid_pv}")
					# trouver responssable

					return JsonResponse({"uuid_pv": uuid_pv, "tag_id_cm": tag_id_cm},status=status.HTTP_201_CREATED)

			# carte cliente
			if testCard["type_card"] == "client_card":
				print("laboutik - DEV | c'est une carte client")
				return JsonResponse({"msg": _("Carte non primaire")},status=status.HTTP_400_BAD_REQUEST)
			
			# carte inconnue
			if testCard["type_card"] == "unknown":
				return JsonResponse({"msg": _("Carte inconnue")},status=status.HTTP_400_BAD_REQUEST)

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
		'pv': pv,
		'configuration': mockData.configuration
	}
	return render(request, "components/show_pv.html", context)


def pv_route(request):
	uuid_pv = request.GET.get('uuid_pv')
	tag_id_cm = request.GET.get('tag_id_cm')
	print(f"laboutik - DEV | uuid_pv = {uuid_pv}  --  tag_id_cm = {tag_id_cm}")
	pv = mockData.get_pv_from_uuid(uuid_pv)
	card = mockData.get_card_from_tagid(tag_id_cm)
	# restaurent par défaut
	template = 'restaurant.html'
	
	# service directe
	if pv['service_direct'] == True:
		template = 'direct_service.html'

	# kiosque
	if pv['comportement'] == 'K':
		template = 'kiosk.html'


	print(f"laboutik - DEV | template = {template}")
	context = {
		'state': state,
    'stateJson': dumps(state),
		'pv': pv,
		'card': card,
		'configuration': mockData.configuration
	}
	return render(request, "views/" + template, context)