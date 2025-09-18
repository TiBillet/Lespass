from django.shortcuts import render
import sys
from pathlib import Path

# Ajoutez le répertoire utils au chemin d'importation
# Path(__file__) = /DjangoFiles/laboutik/views.py
sys.path.append(str(Path(__file__).resolve().parent / "utils"))

import mockData

def login_hardware(request):
	print(f"chemin = {Path(__file__)}")
	print(f"pvs = {mockData.pvs}")
	return render(request, "views/login_hardware.html", context={})