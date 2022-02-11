import os
from datetime import timedelta, datetime
from os.path import exists
import requests
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import schema_context, tenant_context
from random import randrange
from AuthBillet.models import TibilletUser
from Customers.models import Client, Domain
import os, json
from django.core.management import call_command
from django.utils.text import slugify


class Command(BaseCommand):

    def handle(self, *args, **options):
        # Création du tenant principal public
        tenant_public, created = Client.objects.get_or_create(
            schema_name='public',
            name=os.environ.get('PUBLIC'),
            on_trial=False,
            categorie=Client.META,
        )
        tenant_public.save()

        domain_public, created = Domain.objects.get_or_create(
            domain=f'{os.getenv("DOMAIN")}',
            tenant=tenant_public,
            is_primary=True
        )
        domain_public.save()

        tenant_demo, created = Client.objects.get_or_create(
            schema_name="demo",
            name="Demo",
            on_trial=False,
            categorie=Client.SALLE_SPECTACLE,
        )
        tenant_demo.save()

        domain_demo, created = Domain.objects.get_or_create(
            domain=f'demo.{os.getenv("DOMAIN")}',
            tenant=tenant_demo,
            is_primary=True
        )
        domain_demo.save()

        # with schema_context('demo'):
        #     call_command('flush')

        # base_url = f"https://demo.{os.environ.get('DOMAIN')}"
        sub_domain = "demo"

        protocol = "http://"
        port = ":8002"
        # protocol = "https://"
        # port = ""
        # domain = os.environ.get('DOMAIN')

        base_url = f"{protocol}{sub_domain}.{os.environ.get('DOMAIN')}{port}"

        # demo_base_url = f"https://demo.{os.environ.get('DOMAIN')}"
        headers = {"charset": "utf-8"}

        email = os.environ.get('EMAIL')
        dummypassword = 'proutprout123'

        ### Create User :
        print("************ Create User")
        url = f"{base_url}/api/user/create/"
        data_json = {
            'email': email,
            'password': dummypassword,
        }

        response = requests.request("POST", url, data=data_json)
        # print(response.text)
        with schema_context('Demo'):
            User: TibilletUser = get_user_model()
            admin = User.objects.get(email=email)
            admin.is_active = True
            admin.can_create_tenant = True
            admin.is_staff = True
            admin.client_admin.add(Client.objects.get(name="Demo"))
            admin.save()

        # assert response.status_code == 200
        print("************ Create User OK")

        ### Get Token user :
        print("************ Create Get Token user")
        url = f"{base_url}/api/user/token/"
        data_json = {'username': email,
                     'password': dummypassword}
        response = requests.request("POST", url, data=data_json)
        auth_token = response.json().get("access")
        assert auth_token

        headers['Authorization'] = f"Bearer {auth_token}"
        print("************ Create Get Token user OK")

        ### me :
        print("************ me")

        url = f"{base_url}/auth/users/me/"
        response = requests.request("GET", url, headers=headers, data=data_json)

        # print(response.text)
        assert response.status_code == 200
        print("************ me OK")

        ## create tenant from demo file
        from data.domains_and_cards import tenants

        for organisation, place in tenants.items():
            place: dict
            print(f"************ Create TENANT {organisation}")
            domains = [slugify(organisation), ]
            if place.get('domains'):
                domains = place.get('domains')

            if place.get("categorie") == "S":
                url = f"{base_url}/api/place/"
            elif place.get("categorie") == "A":
                url = f"{base_url}/api/artist/"

            data_json = {
                'organisation': organisation,
                'domains': domains,
                'short_description': place.get('short_description'),
                'long_description': place.get('long_description'),
                'phone': place.get("phone"),
                'email': place.get("email"),
                'postal_code': place.get("postal_code"),
                'categorie': place.get("categorie"),
            }

            files = []
            if place.get('img'):
                files.append(
                    ('img',
                     (place.get('img'), open(f"/DjangoFiles/data/demo_img/{place.get('img')}", 'rb'), 'image/png'))
                )
            if place.get('logo'):
                files.append(
                    ('logo',
                     (place.get('logo'), open(f"/DjangoFiles/data/demo_img/{place.get('logo')}", 'rb'), 'image/png'))
                )
            print('*' * 30)
            print(f'on lance la requete : {url}')
            print('*' * 30)
            response = requests.request("POST", url, headers=headers, data=data_json, files=files)
            # print(response.text)

            if response.status_code == 409:
                print("Conflict : Existe déja, on lance un put")
                uuid = json.loads(response.json()).get("uuid")
                url_put = f"{url}{uuid}/"
                # on envoie le txt avec requests
                response = requests.request("PUT", url_put, headers=headers, data=data_json)

                # requests ne sachant pas envoye de fichier en PUT, on passe par curl
                if place.get('img'):
                    command = f"curl --location " \
                              f"-H 'Authorization: Bearer {auth_token}' " \
                              f"--request PUT '{base_url}/api/place/{uuid}/' " \
                              f"--form 'img=@\"/DjangoFiles/data/demo_img/{place.get('img')}\"'"
                    os.system(command)

                if place.get('logo'):
                    command = f"curl --location " \
                              f"-H 'Authorization: Bearer {auth_token}' " \
                              f"--request PUT '{base_url}/api/place/{uuid}/' " \
                              f"--form 'logo=@\"/DjangoFiles/data/demo_img/{place.get('logo')}\"'"
                    os.system(command)

            print(f"\n")
            print(f"************ Create TENANT {organisation} OK")
            print(f"\n")

        salles = requests.request("GET", f"{base_url}/api/place/").json()
        artists = requests.request("GET", f"{base_url}/api/artist/").json()

        for salle in salles:
            sub_domain = f"{salle.get('slug')}"
            base_url = f"{protocol}{sub_domain}.{os.environ.get('DOMAIN')}{port}"

            url = f"{base_url}/api/user/token/"
            data_json = {'username': email,
                         'password': dummypassword}
            response = requests.request("POST", url, data=data_json)
            auth_token = response.json().get("auth_token")
            headers = { 'Authorization': f"Bearer {auth_token}" }

            ### Create product
            print("\n")
            print("************ Create Ticket Product")

            url = f"{base_url}/api/products/"
            data_json = {'name': 'Billet',
                         'publish': 'true',
                         'categorie_article': 'B'}
            files = [
                ('img', ('tickets_old.png', open('/DjangoFiles/data/demo_img/tickets.png', 'rb'), 'image/png'))
            ]
            print('*' * 30)
            print(f'on lance la requete : {url}')
            response = requests.request("POST", url, headers=headers, data=data_json, files=files)
            print('*' * 30)

            uuid_ticket_product = response.json().get("uuid")
            # print(response.text)
            if response.status_code not in [201, 409]:
                import ipdb; ipdb.set_trace()

            print("************ Create Ticket Product OK")
            print("\n")

            if response.status_code == 201:
                ### Create Ticket prices
                print("\n")
                print("************ Create Ticket prices")
                url = f"{base_url}/api/prices/"

                data_json = {'name': 'Demi Tarif',
                             'prix': '5',
                             'vat': 'NA',
                             'max_per_user': '10',
                             'stock': '250',
                             'product': uuid_ticket_product}
                response = requests.request("POST", url, headers=headers, data=data_json)
                uuid_price_demi = response.json().get("uuid")
                # print(response.text)
                assert response.status_code == 201

                data_json = {'name': 'Plein Tarif',
                             'prix': '10',
                             'vat': 'NA',
                             'max_per_user': '10',
                             'stock': '250',
                             'product': uuid_ticket_product}
                response = requests.request("POST", url, headers=headers, data=data_json)
                uuid_price_plein = response.json().get("uuid")
                # print(response.text)
                assert response.status_code == 201
                print("************ Create Ticket prices OK")
                print("\n")

            ### Create TShirt product
            print("\n")
            print("************ Create TShirt Product")
            url = f"{base_url}/api/products/"
            data_json = {'name': 'TShirt',
                         'publish': 'true',
                         'categorie_article': 'T'}
            files = [
                ('img', ('tshirt.png', open('/DjangoFiles/data/demo_img/tshirt.png', 'rb'), 'image/png'))
            ]
            response = requests.request("POST", url, headers=headers, data=data_json, files=files)
            uuid_tshirt_product = response.json().get("uuid")
            # print(response.text)
            assert response.status_code in [201, 409]
            print("************ Create TShirt Product OK")
            print("\n")

            if response.status_code == 201:
                ### Create Ticket prices
                print("\n")
                print("************ Create TShirt prices")
                url = f"{base_url}/api/prices/"

                data_json = {'name': 'S',
                             'prix': '5',
                             'vat': 'NA',
                             'max_per_user': '10',
                             'stock': '250',
                             'product': uuid_tshirt_product}
                response = requests.request("POST", url, headers=headers, data=data_json)
                uuid_tshirt_s = response.json().get("uuid")
                # print(response.text)
                assert response.status_code == 201

                data_json = {'name': 'L',
                             'prix': '5',
                             'vat': 'NA',
                             'max_per_user': '10',
                             'stock': '250',
                             'product': uuid_tshirt_product}
                response = requests.request("POST", url, headers=headers, data=data_json)
                uuid_tshirt_l = response.json().get("uuid")
                # print(response.text)
                assert response.status_code == 201
                print("************ Create TShirt prices OK")
                print("\n")

            print("\n")
            print("************ Event Générator")

            url = f"{base_url}/api/products/"
            print('*' * 30)
            print(f'on lance la requete : {url}')
            products = requests.request("GET", url).json()
            products_uuid = [product.get('uuid') for product in products]
            print('*' * 30)

            def random_date():
                """
                This function will return a random datetime between two datetime
                objects.
                """
                delta = timedelta(days=360)
                int_delta = (delta.days * 24 * 60 * 60) + delta.seconds
                random_second = randrange(int_delta)
                return datetime.now() + timedelta(seconds=random_second)

            for artist in artists:
                r_date = random_date()
                headers["Content-type"] = "application/json"
                data_json = {
                    'date': r_date.date().strftime("%Y-%m-%d"),
                    'artists': [
                        {
                            "uuid": artist.get('uuid'),
                            "datetime": r_date.strftime("%Y-%m-%dT%H:%M")
                        },
                    ],
                    "products": products_uuid
                }

                url = f"{base_url}/api/events/"
                print('*' * 30)
                print(f'on lance la requete : {url}')
                response = requests.request("POST", url, headers=headers, data=json.dumps(data_json))
                print('*' * 30)
                if response.status_code == 415:
                    import ipdb;
                    ipdb.set_trace()
                # print(response.text)

            r_date = random_date()
            headers["Content_type"] = "application/json"
            data_json = {
                'date': r_date.date().strftime("%Y-%m-%d"),
                'artists': [
                    {
                        "uuid": artists[0].get('uuid'),
                        "datetime": r_date.strftime("%Y-%m-%dT%H:%M")
                    },
                    {
                        "uuid": artists[1].get('uuid'),
                        "datetime": (r_date + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
                    },
                ],
                "products": products_uuid
            }
            response = requests.request("POST", f"{base_url}/api/events/", headers=headers, data=json.dumps(data_json))
            # print(response.text)

            r_date = random_date()
            headers["Content_type"] = "application/json"
            data_json = {
                'date': r_date.date().strftime("%Y-%m-%d"),
                'artists': [
                    {
                        "uuid": artists[2].get('uuid'),
                        "datetime": r_date.strftime("%Y-%m-%dT%H:%M")
                    },
                    {
                        "uuid": artists[3].get('uuid'),
                        "datetime": (r_date + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
                    },
                ],
                "products": products_uuid
            }
            response = requests.request("POST", f"{base_url}/api/events/", headers=headers, data=json.dumps(data_json))
            # print(response.text)
