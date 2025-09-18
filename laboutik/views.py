from django.shortcuts import render
from django.http import JsonResponse, HttpResponseNotFound, HttpResponseNotAllowed
from django.conf import settings
from rest_framework import status
from django.utils.translation import gettext as _

import sys
from pathlib import Path

# Ajoutez le répertoire utils au chemin d'importation
# Path(__file__) = /DjangoFiles/laboutik/views.py
sys.path.append(str(Path(__file__).resolve().parent / "utils"))

import mockData

def login_hardware(request):
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

	# print(f"pvs = {mockData.pvs}")
	print(f"settings = {settings.DEMO}")
	context = {
		'demo': settings.DEMO
	}
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

def home(request):
	return render(request, "views/home.html", context={})