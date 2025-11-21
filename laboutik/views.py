from django.shortcuts import render
from django.http import HttpResponse
from django.template import Template, RequestContext
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

# db mock
db = mockData.mockDb("./laboutik/utils/mockDb.json")

data_pvs = mockData.get_data_pvs()

state = {
  "version": "0.9.11",
  "place": {
    "name": "lieu de test",
    "monnaie_name": "lémien" 
  },
  "demo": {
    "active": settings.DEMO,
    "tags_id": [
      {"tag_id": settings.DEMO_TAGID_CM, "name": _("Carte primaire")},
      {"tag_id": settings.DEMO_TAGID_CLIENT1, "name": _("Carte client 1")},
      {"tag_id": settings.DEMO_TAGID_CLIENT2, "name": _("Carte client 2")},
      {"tag_id": settings.DEMO_TAGID_CLIENT3, "name": _("Carte client 3")},
      {"tag_id": settings.DEMO_TAGID_UNKNOWN, "name": _("Carte client inconnu")},
    ],
  }
}

currency_data = {"cc": "EUR", "symbol": "€", "name": "European Euro"}

payments_translation = {
  "nfc": _("cashless"),
  "espece": _("espèce"),
  "carte_bancaire": _("carte bancaire"),
  "CH": _("chèque"),
  "gift": _("cadeau"),
	"": _("inconnu")
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

  # hardware activé
  if devHardwareOk:
    # Le code pin a été validé, on renvoie vers la page de login
    return HttpResponseClientRedirect("login_hardware?activation=1")

  # error
  if not devHardwareOk:
    context = {
      "error": _(
        "Appareil déja en cours d'utilisation. Désactivez le d'abord pour un nouvel appairage."
      )
    }
    return render(request, "components/new-hardware-error.html", context)


def hx_check_card(request):
  background = "--success"
  context = {"method": request.method}

  if request.method == "POST":
    tag_id = request.POST.get("tag_id").upper()
    context["tag_id"] = tag_id

    # dev
    card = db.get_by_index("cards", "tag_id", tag_id)[0]
    background = "--warning"
    card["type_card"] = "unknown"

    if card["type_card"] == "unknown":
      background = "--rouge06"
      error_msg = _("Carte inconnue")

  context["error_msg"] = error_msg
  context["background"] = background
  # print(f"-- context = {context}")
  return render(request, "partial/hx_check_card.html", context)


def ask_primary_card(request):
  context = {"state": state, "stateJson": dumps(state), "method": request.method}
  if request.method == "POST":
    tag_id_cm = request.POST.get("tag_id").upper()

    # dev
    carte_perdu = False
    card = {}
    if tag_id_cm == 'XXXXXXXX':
      card["type_card"] = "unknown"
    else:
      card = db.get_by_index("cards", "tag_id", tag_id_cm)[0]

    # carte primaire
    if card["type_card"] == "primary_card" and card["tag_id"] == "A49E8E2A":
      # carte perdue
      if carte_perdu:
        template = Template(_("Carte perdue ? non primaire"))
        context = RequestContext(request)
        return HttpResponse(template.render(context))
      else:
        # carte primaire ok => redirection
        uuid_pv = card["pvs_list"][0]["uuid"]
        return HttpResponseClientRedirect("pv_route?uuid_pv=" + uuid_pv + "&tag_id_cm=" + tag_id_cm)

    # carte cliente
    if card["type_card"] == "client_card":
      template = Template(_("Carte non primaire"))
      context = RequestContext(request)
      return HttpResponse(template.render(context))

    # carte inconnue
    if card["type_card"] == "unknown":
      template = Template(_("Carte inconnue"))
      context = RequestContext(request)
      return HttpResponse(template.render(context))

  return render(request, "views/ask_primary_card.html", context)


def pv_route(request):
  # pour un mode restaurant (non service direct)
  try:
    id_table = int(request.GET.get("id_table"))
  except:
    id_table = None

  # force le service direct en mode restaurant
  force_service_direct = True if request.GET.get("force_service_direct") == "true" else None

  # mode restaurant forcer en service direct
  restaurant_service_direct = request.GET.get("restaurant_service_direct")
  uuid_pv = request.GET.get("uuid_pv")
  tag_id_cm = request.GET.get("tag_id_cm")
  pv = mockData.get_pv_from_uuid(uuid_pv, data_pvs)
  card = db.get_by_index("cards", "tag_id", tag_id_cm)[0]
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
  state["mode_gerant"] = card["mode_gerant"]
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
    "currency_data": currency_data,
    "uuidArticlePaiementFractionne": "42ffe511-d880-4964-9b96-0981a9fe4071",
    "id_table": id_table,
  }
  return render(request, "views/" + template, context)


def hx_display_type_payment(request):
  dataPost = request.POST
  uuid_pv = dataPost.get("uuid_pv")

  # récupère uniquement les uuid articles
  uuids = method.post_filter(request.POST)

  # obtenir le point de vente en fonction de son uuid
  pv = mockData.get_pv_from_uuid(uuid_pv, data_pvs)

  # retourne les moyens de paiement nécessaires et filtrés par moyens de paiement acceptés
  moyens_paiement = method.selection_moyens_paiement(pv, uuids, request.POST)

  # import ipdb; ipdb.set_trace()
  # calcul du total de l'addition
  total = method.calcul_total_addition(pv, uuids, request.POST)

  # dev mock
  mode_gerant = False

  # dev mock (article consigne présent)
  deposit_is_present = False

  context = {
    "moyens_paiement": moyens_paiement,
    "currency_data": currency_data,
    "total": total,
    "mode_gerant": mode_gerant,
    "deposit_is_present": deposit_is_present,
    "comportement": pv["comportement"],
  }

  return render(request, "partial/hx_display_type_payment.html", context)


def hx_read_nfc(request):
  uuid_transaction = "" if request.GET.get("uuid_transaction") == None else request.GET.get("uuid_transaction")
  context = {"uuid_transaction": uuid_transaction}
  return render(request, "partial/hx_read_nfc.html", context)


def hx_confirm_payment(request):
  payment_method = request.GET.get("method")
  uuid_transaction = request.GET.get("uuid_transaction")
  context = {
    "method": payment_method, 
    "payment_translation": payments_translation[payment_method],
    "uuid_transaction": uuid_transaction
  }
  return render(request, "partial/hx_confirm_payment.html", context)


def hx_payment(request):
  # msg_type = success, info, error, warning
  payment = request.POST.dict()

	# total achats
  payment["total"] = int(payment["total"])

 
  # dev mock: db and payment success ?
	# default
  payment["success"] = True
  if payment["moyen_paiement"] == "nfc" and payment.get("tag_id"):
    card = db.get_by_index('cards', 'tag_id', payment['tag_id'])[0]
    payment["card_name"] = card["name"]
    payment["wallets"] = {
      "monnaie": card["wallets"],
      "gift_monnaie": card["wallets_gift"]
    }
    wallets = (float(card["wallets"]) * 100) + (float(card["wallets_gift"]) * 100) 
    payment["funds_insufficient"] = False
    if payment["total"] > wallets:
      payment["success"] = False
      payment["funds_insufficient"] = True
      payment["missing"] = (payment["total"] - wallets) / 100

  print(f"-------- payment = ${payment}")

  # transaction (complémentaire)
  uuid_transaction = payment["uuid_transaction"] if payment.get("uuid_transaction") else ""
  # payment step
  step = 2
  
  # step 1, record funds insufficient (data card 1)
  payment_card1 = None
  if uuid_transaction == "":
    step = 1
    # print(f'--- ajout transaction dans db ---')
    uuid_transaction = db.add('transactions', {
      "payment": payment
    })
  else:
    payment_card1 = db.get_by_index('transactions', 'id', uuid_transaction)[0]['payment']
    # print(f'crédits complémentaires donnés')

  if payment["success"]:
	  # somme donnée
    if payment.get("given_sum"):
      payment["give_back"] = (float(payment["given_sum"]) - float(payment["total"])) / 100
      payment["given_sum"] = float(payment["given_sum"]) / 100
      print(f'moyen_paiement = {payment["moyen_paiement"]}')

    # plus en centimes
    payment["total"] = payment["total"] / 100
    context = {
      "currency_data": currency_data,
      "payment": payment,
			"payment_card1": payment_card1,
      "monnaie_name": state["place"]["monnaie_name"],
      "moyen_paiement": payments_translation[payment["moyen_paiement"]]
    }
    return render(request, "partial/hx_payment_success.html", context)

  if payment["success"] == False:
    if payment_card1 and payment_card1.get('tag_id') == payment.get('tag_id') and step == 2:
      context = {
		    "msg_type": "warning",
			  "msg_content": _("Vous utilisez la même carte !")
			}
      return render(request, "partial/hx_messages.html", context)

    if payment["funds_insufficient"]:
      card = db.get_by_index('cards', 'tag_id', payment['tag_id'])[0]
      pv = db.get_by_index('pvs', 'id', payment['uuid_pv'])[0]
      context = {
				"currency_data": currency_data,
      	"payment": payment,
        "card": card,
        "wallets": {
          "monnaie": card["wallets"],
          "gift_monnaie": card["wallets_gift"]
        },
        "monnaie_name": state["place"]["monnaie_name"],
        "payments_accepted": {
          "accepte_especes": pv["accepte_especes"],
  	      "accepte_carte_bancaire": pv["accepte_carte_bancaire"],
  	      "accepte_cheque": pv["accepte_cheque"]
        },
        "uuid_transaction": uuid_transaction,
				"step": step
			}
      return render(request, "partial/hx_funds_insufficient.html", context)

    context = {
      "msg_type": "warning",
      "msg_content": "Il y a une erreur !",
      "selector_bt_retour": "#messages",
    }
    return render(request, "partial/hx_messages.html", context)
