import requests, json
from django.contrib.auth import get_user_model
from django.db import connection
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.shortcuts import render
from django.utils import timezone
from rest_framework.generics import get_object_or_404

import stripe

# Create your views here.
from django.views import View
from rest_framework import status
from rest_framework.response import Response

from AuthBillet.models import TibilletUser, HumanUser
from BaseBillet.models import Configuration, Article
from PaiementStripe.models import Paiement_stripe
from QrcodeCashless.models import CarteCashless
import logging
logger = logging.getLogger(__name__)


def get_domain(request):
    absolute_uri = request.build_absolute_uri()
    for domain in request.tenant.domains.all():
        if domain.domain in absolute_uri:
            return domain.domain

    raise Http404

def check_carte_local(uuid):
    carte = get_object_or_404(CarteCashless, uuid=uuid)
    return carte

class gen_one_bisik(View):
    def get(self, request, numero_carte):
        print(numero_carte)
        carte = get_object_or_404(CarteCashless, number=numero_carte)
        address = request.build_absolute_uri()
        return HttpResponseRedirect(
            address.replace("://m.", "://bisik.").replace(f"{carte.number}", f"qr/{carte.uuid}"))


class index_scan(View):
    # template_name = "RechargementWebUuid.html"
    template_name = "html5up-dimension/index.html"

    def check_carte_serveur_cashless(self, uuid):
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
            reponse = HttpResponse("Serveur non disponible. Merci de revenir ultérieurement.",
                                   status=status.HTTP_503_SERVICE_UNAVAILABLE)

        sess.close()
        return reponse

    def get(self, request, uuid):
        carte = check_carte_local(uuid)
        if carte.detail.origine != connection.tenant:
            raise Http404

        # dette technique ...
        # pour rediriger les premières générations de qrcode
        # m.tibillet.re et raffinerie

        address = request.build_absolute_uri()
        host = address.partition('://')[2]
        sub_addr = host.partition('.')[0]
        if sub_addr == "m":
            return HttpResponseRedirect(address.replace("://m.", "://raffinerie."))

        configuration = Configuration.get_solo()
        if not configuration.server_cashless:
            return HttpResponse(
                "L'adresse du serveur cashless n'est pas renseignée dans la configuration de la billetterie.")
        if not configuration.stripe_api_key or not configuration.stripe_test_api_key:
            return HttpResponse(
                "Pas d'information de configuration pour paiement en ligne.")

        reponse_server_cashless = self.check_carte_serveur_cashless(carte.uuid)
        if reponse_server_cashless.status_code == 200:
            json_reponse = json.loads(reponse_server_cashless.json())
            liste_assets = json_reponse.get('liste_assets')
            email = json_reponse.get('email')

            return render(
                request,
                self.template_name,
                {
                    'carte_resto': configuration.carte_restaurant,
                    'site_web': configuration.site_web,
                    'url_image_carte': carte.detail.img_url,
                    'numero_carte': carte.number,
                    'client_name': carte.detail.origine.name,
                    'domain': sub_addr,
                    'informations_carte': reponse_server_cashless.text,
                    'liste_assets': liste_assets,
                    'email': email,
                }
            )


        elif reponse_server_cashless.status_code == 400:
            # Carte non trouvée
            return HttpResponse('Carte inconnue', status=status.HTTP_400_BAD_REQUEST)
        elif reponse_server_cashless.status_code in (500, 503):
            # Serveur cashless hors ligne
            return reponse_server_cashless

    def post(self, request, uuid):
        carte = check_carte_local(uuid)
        if carte.detail.origine != connection.tenant:
            raise Http404

        data = request.POST
        reponse_server_cashless = self.check_carte_serveur_cashless(carte.uuid)
        montant_recharge = float("{0:.2f}".format(float(data.get('montant_recharge'))))
        configuration = Configuration.get_solo()

        if reponse_server_cashless.status_code == 200 and \
                montant_recharge > 0:

            User = get_user_model()
            user_recharge, created = User.objects.get_or_create(
                email=data.get('email'))
            if created:
                user_recharge: HumanUser
                user_recharge.client_source = connection.tenant
                user_recharge.client_achat.add(connection.tenant)
                user_recharge.is_active = False
            else:
                user_recharge.client_achat.add(connection.tenant)
            user_recharge.save()

            art, created = Article.objects.get_or_create(
                name="Recharge Stripe",
                prix="1",
                publish=False,
            )


            metadata = {
                'recharge_carte_uuid': str(carte.uuid),
                'recharge_carte_montant': str(montant_recharge),
            }
            metadata_json = json.dumps(metadata)

            paiementStripe = Paiement_stripe.objects.create(
                user=user_recharge,
                detail=f"{art.name}",
                total=montant_recharge,
                metadata_stripe=metadata_json,
            )

            absolute_domain = request.build_absolute_uri().partition('/qr')[0]

            if configuration.stripe_mode_test:
                stripe.api_key = configuration.stripe_test_api_key
            else:
                stripe.api_key = configuration.stripe_api_key

            checkout_session = stripe.checkout.Session.create(
                customer_email=f'{user_recharge.email}',
                line_items=[{
                    'price_data': {
                        'currency': 'eur',

                        'product_data': {
                            'name': 'Recharge Cashless',
                            "images": [f'{carte.detail.img_url}', ],
                        },
                        'unit_amount': int("{0:.2f}".format(montant_recharge).replace('.', '')),
                    },
                    'quantity': 1,

                }],
                payment_method_types=[
                    'card',
                ],
                mode='payment',
                metadata=metadata,
                success_url=f'{absolute_domain}/stripe/return/{paiementStripe.uuid}',
                cancel_url=f'{absolute_domain}/stripe/return/{paiementStripe.uuid}',
                # submit_type='Go go go',
                client_reference_id=f"{data.get('numero_carte_cashless')}",
            )

            print(checkout_session.id)
            paiementStripe.id_stripe = checkout_session.id
            paiementStripe.status = Paiement_stripe.PENDING
            paiementStripe.save()

            return HttpResponseRedirect(checkout_session.url)


def postPaimentRecharge(paiementStripe: Paiement_stripe, request):
    if paiementStripe.status == Paiement_stripe.PAID:

        metadata_db_json = paiementStripe.metadata_stripe
        metadata_db = json.loads(metadata_db_json)
        uuid_carte = metadata_db.get('recharge_carte_uuid')
        total_rechargement = metadata_db.get('recharge_carte_montant')

        if uuid_carte and total_rechargement :


            # on vérifie toujours que la carte vienne bien du domain et Client tenant.
            carte = check_carte_local(uuid_carte)
            if carte.detail.origine != connection.tenant:
                logger.error(f"{timezone.now()} "
                             f"postPaimentRecharge {uuid_carte} : "
                             f"carte detail origine correspond pas : {carte.detail.origine} != {connection.tenant}")
                raise Http404

            sess = requests.Session()
            configuration = Configuration.get_solo()
            r = sess.post(f'{configuration.server_cashless}/api/rechargementPaid',
                          headers={
                              'Authorization': f'Api-Key {configuration.key_cashless}'
                          },
                          data={
                              'uuid_carte': uuid_carte,
                              'qty': float(total_rechargement),
                              'uuid_commande': paiementStripe.uuid,
                          })

            sess.close()

            if r.status_code == 200:
                # la commande a été envoyé au serveur cashless, on la met en validée
                paiementStripe.status = Paiement_stripe.VALID
                paiementStripe.save()

                absolute_domain = request.build_absolute_uri().partition('/stripe/return')[0]
                return HttpResponseRedirect(f'{absolute_domain}/qr/{uuid_carte}#historique')

        elif paiementStripe.status == Paiement_stripe.VALID:
            # Le paiement a bien été accepté par le passé et envoyé au serveur cashless.
            return HttpResponse(
                f"<center><h1>Le paiement a déja été validé. Vous avez bien rechargé votre carte !</h1></center>")

        return HttpResponse("<center><h1>Paiement non valide. Contactez un responsable.<h1></center>")
