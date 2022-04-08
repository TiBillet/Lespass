import datetime
import json
import logging, os
import threading
import time
import uuid

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import tenant_context

from BaseBillet.models import Paiement_stripe
from Customers.models import Client


class Command(BaseCommand):

    def handle(self, *args, **options):

        email = os.environ.get('EMAIL')
        dummypassword = os.environ.get('DEMODATA_PASSWORD')
        if not dummypassword:
            print(f'password for user {email}')
            dummypassword = input()

        tenant_m = Client.objects.get(
            schema_name="m",
        )

        protocol = "http://"
        port = ":8002"
        # protocol = "https://"
        # port = ""

        base_url_default = f"{protocol}m.{os.environ.get('DOMAIN')}{port}"
        print(f'url par default : {base_url_default}. ENTER pour valider, remplacez sinon')
        base_url = input()
        if not base_url:
            base_url = base_url_default

        ### Get Token user :
        print("************ Create Get Token user")
        url = f"{base_url}/api/user/token/"
        data_json = {'username': email,
                     'password': dummypassword}
        response = requests.request("POST", url, data=data_json)
        auth_token = response.json().get("access")
        assert auth_token
        headers = {'Authorization': f"Bearer {auth_token}"}
        print("************ Create Get Token user OK")

        def artists():
            artists = requests.request("GET", f"{base_url}/api/artist/").json()
            return artists

        def products():
            url = f"{base_url}/api/products/"
            products = requests.request("GET", url).json()
            products_uuid = [product.get('uuid') for product in products]
            return products_uuid

        def options():
            req_options = requests.request("GET", f"{base_url}/api/optionticket/").json()
            options_uuid = [option.get('uuid') for option in req_options]
            return options_uuid

        def create_event():
            artist = artists()[0]
            r_date = datetime.datetime.now().date()
            headers["Content-type"] = "application/json"
            data_json = {
                'date': r_date.strftime("%Y-%m-%d"),
                'artists': [
                    {
                        "uuid": artist.get('uuid'),
                        "datetime": r_date.strftime("%Y-%m-%dT23:00")
                    },
                ],
                "products": products(),
                "options_radio": options()[:2],
                "options_checkbox": options()[2:],
            }

            url = f"{base_url}/api/events/"
            print(f'on lance la requete : {url}')
            print('*' * 30)
            response = requests.request("POST", url, headers=headers, data=json.dumps(data_json)).json()
            print('*' * 30)
            return response

        def gen_random_string():
            return str(uuid.uuid4()).split("-")[0]

        def create_reservations(nbr):
            event = create_event()
            event_uuid = event.get('uuid')

            price_uuid = ""
            for product in event.get('products'):
                if product.get('categorie_article') == 'B':
                    price_uuid = product.get('prices')[0]['uuid']


            def request_resa():
                headers["Content-type"] = "application/json"
                data_json = {
                    "event": f"{event_uuid}",
                    "email": f"{gen_random_string()}@{gen_random_string()}.com",
                    "to_mail": False,
                    "prices": [
                        {
                            "uuid": f"{price_uuid}",
                            "qty": 2,
                            "customers": [
                                {
                                    "first_name": f"Prenom{gen_random_string()}",
                                    "last_name": f"Nom{gen_random_string()}"
                                },
                                {
                                    "first_name": f"Prenom{gen_random_string()}",
                                    "last_name": f"Nom{gen_random_string()}"
                                }
                            ]
                        }
                    ]
                }

                url = f"{base_url}/api/reservations/"
                print(f'on lance la requete : {url}')
                print('*' * 30)
                response = requests.request("POST", url, headers=headers, data=json.dumps(data_json)).json()
                print(response)
                print('*' * 30)
                if response.get('paiement_stripe_uuid'):
                    with tenant_context(tenant_m):
                        ordre = Paiement_stripe.objects.get(uuid=response.get('paiement_stripe_uuid'))
                        ordre.status = Paiement_stripe.PAID
                        ordre.save()

                return response

            # multi thread pour benchmark
            for x in range(0, nbr):
                time.sleep(0.2)
                print(f'{timezone.now()} on lance le thread request_resa')
                thread_email = threading.Thread(target=request_resa)
                thread_email.start()
                print(f'{timezone.now()} Thread resa lancé')

            '''
            with tenant_context(tenant_m):
                for ordre in Paiement_stripe.objects.filter(
                        reservation__event__uuid=event_uuid
                ):
                    ordre.status = Paiement_stripe.PAID
                    ordre.save()

            '''

        create_reservations(300)
