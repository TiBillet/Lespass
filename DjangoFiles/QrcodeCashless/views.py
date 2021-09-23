import requests, json
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render

# Create your views here.
from django.views import View
from rest_framework import status
from rest_framework.response import Response

from BaseBillet.models import Configuration


class index_scan(View):
    template_name = "RechargementWebUuid.html"

    def check_carte(self, uuid):
        configuration = Configuration.get_solo()
        # on questionne le serveur cashless pour voir si la carte existe :

        sess = requests.Session()
        try:
            reponse = sess.post(
                f'{configuration.server_cashless}/api/billetterie_endpoint',
                headers={
                    'Authorization': f'Api-Key {configuration.key_cashless}'
                },
                data={
                    'uuid': f'{uuid}',
                })
        except requests.exceptions.ConnectionError:
            reponse = HttpResponse("Serveur non disponible. Merci de revenir ultérieurement.", status=status.HTTP_503_SERVICE_UNAVAILABLE)

        sess.close()
        return reponse

    def post(self, request, uuid):
        data = request.POST
        reponse_server_cashless = self.check_carte(uuid)

        if data.get('numero_carte_cashless') == str(uuid).split('-')[0].upper() and \
                reponse_server_cashless.status_code == 200:

            userWeb, created = User.objects.get_or_create(
                username="RechargementWeb",
                email="rechargementweb@tibillet.re")

            vat, created = VAT.objects.get_or_create(percent=0)

            commande = Commande.objects.create(
                user=userWeb,
                email_billet=data.get('email'),
            )

            art, created = Product.objects.get_or_create(
                name="CashlessRechargementWeb",
                price_ttc="1",
                publish=False,
                vat=vat
            )

            ArticleCommande.objects.create(
                product=art,
                quantity=data.get('thune'),
                commande=commande,
            )

            domain = get_domain(request)
            sub_domain = str(domain).split('.')[0]
            absolute_domain = request.build_absolute_uri().partition('/qr')[0]

            Paiement = CreationPaiementMollie(commande, domain,
                                              description=f"Rechargez votre carte {sub_domain.capitalize()}",
                                              redirectUrl=f"{absolute_domain}/RechargementWebAfterMollie/{commande.uuid}",
                                              webhookUrl=f"{absolute_domain}/RechargementWebAfterMollie/{commande.uuid}",
                                              numero_carte_cashless=data.get('numero_carte_cashless'))

            if Paiement.is_send():
                return HttpResponseRedirect(Paiement.is_send())


    def get(self, request, uuid):

        # pour rediriger les carte imprimés a la raffinerie vers le bon tenant.
        address = request.build_absolute_uri()
        host = address.partition('://')[2]
        sub_addr = host.partition('.')[0]
        if sub_addr == "m":
            return HttpResponseRedirect(address.replace("://m.", "://raffinerie."))

        configuration = Configuration.get_solo()
        if not configuration.server_cashless:
            return HttpResponse(
                "L'adresse du serveur cashless n'est pas renseignée dans la configuration de la billetterie.")

        reponse_server_cashless = self.check_carte(uuid)
        json_reponse = json.loads(reponse_server_cashless.json())
        liste_assets = json_reponse.get('liste_assets')
        email = json_reponse.get('email')

        if reponse_server_cashless.status_code == 200:
            return render(
                request,
                self.template_name,
                {
                    'numero_carte': str(uuid).split('-')[0].upper(),
                    'domain': sub_addr,
                    'informations_carte': reponse_server_cashless.text,
                    'liste_assets': liste_assets,
                    'email': email,
                }
            )


        elif reponse_server_cashless.status_code == 400:
            # Carte non trouvée
            return HttpResponse('Carte inconnue', status=status.HTTP_400_BAD_REQUEST)
        elif reponse_server_cashless.status_code == 500:
            # Serveur cashless hors ligne
            return reponse_server_cashless