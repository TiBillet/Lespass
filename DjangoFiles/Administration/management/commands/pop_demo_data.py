import logging
import os
import time
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

        tenant_m, created = Client.objects.get_or_create(
            schema_name="m",
            name="m",
            on_trial=False,
            categorie=Client.SALLE_SPECTACLE,
        )
        tenant_m.save()

        domain_m, created = Domain.objects.get_or_create(
            domain=f'm.{os.getenv("DOMAIN")}',
            tenant=tenant_m,
            is_primary=True
        )
        domain_m.save()

        # with schema_context('demo'):
        #     call_command('flush')

        # base_url = f"https://demo.{os.environ.get('DOMAIN')}"
        sub_domain = "m"

        protocol = "http://"
        port = ":8002"
        # protocol = "https://"
        # port = ""

        base_url = f"{protocol}{sub_domain}.{os.environ.get('DOMAIN')}{port}"
        #
        # print(f'url par default : {base_url_default}. ENTER pour valider, remplacez sinon')
        # base_url = input()
        # if not base_url:
        #     base_url=base_url_default

        # demo_base_url = f"https://demo.{os.environ.get('DOMAIN')}"
        headers = {"charset": "utf-8"}

        email = os.environ.get('EMAIL')
        dummypassword = os.environ.get('DEMODATA_PASSWORD')
        if not dummypassword:
            print(f'password for user {email}')
            dummypassword = input()
        ### Create User :
        data_json = {
            'email': email,
            'password': dummypassword,
        }
        url = f"{base_url}/api/user/create/"
        print(f"************ Create User - {url} - data : {data_json}")

        response = requests.request("POST", url, data=data_json)
        print(response.text)

        with tenant_context(tenant_m):
            User: TibilletUser = get_user_model()
            admin = User.objects.get(email=email)
            admin.is_active = True
            admin.can_create_tenant = True
            admin.is_staff = True
            admin.client_admin.add(tenant_m)
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


        url = f"{base_url}/api/user/me/"
        print(f"************ me : {url}")
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
            # if slugify(organisation) == "vavangart":
            #     import ipdb; ipdb.set_trace()

            response = requests.request("POST", url, headers=headers, data=data_json, files=files)

            # try:
            #     response = requests.request("POST", url, headers=headers, data=data_json, files=files)
            # except:
            #     import ipdb; ipdb.set_trace()
            print('*' * 30)

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
            print("\n")
            print(f"************ Get auth token {url}")

            data_json = {'username': email,
                         'password': dummypassword}
            response = requests.request("POST", url, data=data_json)
            auth_token = response.json().get("access")
            headers = { 'Authorization': f"Bearer {auth_token}" }

            ### Create Options pour tickets
            print("\n")
            print("************ Create Options pour tickets")

            url = f"{base_url}/api/optionticket/"
            data_json = {'name': 'Balcon'}
            print('*' * 30)
            print(f'on lance la requete : {url}')
            response = requests.request("POST", url, headers=headers, data=data_json)
            print('*' * 30)

            # print(response.text)
            if response.status_code not in [201, 409]:
                import ipdb; ipdb.set_trace()

            url = f"{base_url}/api/optionticket/"
            data_json = {'name': 'Place assise'}
            print('*' * 30)
            print(f'on lance la requete : {url}')
            response = requests.request("POST", url, headers=headers, data=data_json)
            print('*' * 30)

            url = f"{base_url}/api/optionticket/"
            data_json = {'name': 'Vegetarien'}
            print('*' * 30)
            print(f'on lance la requete : {url}')
            response = requests.request("POST", url, headers=headers, data=data_json)
            print('*' * 30)

            # print(response.text)
            if response.status_code not in [201, 409]:
                import ipdb; ipdb.set_trace()

            url = f"{base_url}/api/optionticket/"
            data_json = {'name': 'Carnivore'}
            print('*' * 30)
            print(f'on lance la requete : {url}')
            response = requests.request("POST", url, headers=headers, data=data_json)
            print('*' * 30)
            # print(response.text)
            if response.status_code not in [201, 409]:
                import ipdb; ipdb.set_trace()



            print("************ Create Options pour tickets OK")
            print("\n")

            ### Create Ticket product
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



            ### Create Adhesion product
            print("\n")
            print("************ Create Adhesion Product")

            url = f"{base_url}/api/products/"
            data_json = {'name': 'Adhesion',
                         'publish': 'true',
                         'categorie_article': 'A'}
            files = [
                ('img', ('adhesion_tampon.png', open('/DjangoFiles/data/demo_img/adhesion_tampon.png', 'rb'), 'image/png'))
            ]
            print('*' * 30)
            print(f'on lance la requete : {url}')
            response = requests.request("POST", url, headers=headers, data=data_json, files=files)
            print('*' * 30)

            uuid_adhesion_prodcut = response.json().get("uuid")
            # print(response.text)
            if response.status_code not in [201, 409]:
                import ipdb; ipdb.set_trace()

            print("************ Create Adhesion Product OK")
            print("\n")

            if response.status_code == 201:
                ### Create Ticket prices
                print("\n")
                print("************ Create Adhesion prices")
                url = f"{base_url}/api/prices/"

                data_json = {'name': 'Tarif solidaire',
                             'prix': '10',
                             'vat': 'NA',
                             'max_per_user': '10',
                             'stock': '250',
                             'product': uuid_adhesion_prodcut}
                response = requests.request("POST", url, headers=headers, data=data_json)
                uuid_price_demi = response.json().get("uuid")
                # print(response.text)
                assert response.status_code == 201

                data_json = {'name': 'Plein Tarif',
                             'prix': '20',
                             'vat': 'NA',
                             'max_per_user': '10',
                             'stock': '250',
                             'product': uuid_adhesion_prodcut}
                response = requests.request("POST", url, headers=headers, data=data_json)
                uuid_price_plein = response.json().get("uuid")
                # print(response.text)
                assert response.status_code == 201

                data_json = {'name': 'Tarif Famille',
                             'prix': '40',
                             'vat': 'NA',
                             'max_per_user': '10',
                             'stock': '250',
                             'product': uuid_adhesion_prodcut}
                response = requests.request("POST", url, headers=headers, data=data_json)
                uuid_price_plein = response.json().get("uuid")
                # print(response.text)
                assert response.status_code == 201

                print("************ Create Adhesion prices OK")
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

            req_options = requests.request("GET", f"{base_url}/api/optionticket/").json()
            options_uuid = [option.get('uuid') for option in req_options]

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
                    'datetime': (r_date - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                    'artists': [
                        {
                            "uuid": artist.get('uuid'),
                            "datetime": r_date.strftime("%Y-%m-%dT%H:%M")
                        },
                    ],
                    "products": products_uuid,
                    "options_radio": options_uuid[:2],
                    "options_checkbox": options_uuid[2:],
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
                'datetime': (r_date - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "img_url": "http://placeimg.com/1920/1080/any.jpg",
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
                'datetime': (r_date - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "img_url": "http://placeimg.com/1920/1080/any.jpg",
                "name": f"{artists[2].get('organisation')} danse avec {artists[3].get('organisation')}",
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

            # et un évènement gratuit, sans produits
            r_date = random_date()
            headers["Content_type"] = "application/json"
            data_json = {
                'datetime': (r_date - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                'artists': [
                    {
                        "uuid": artists[2].get('uuid'),
                        "datetime": r_date.strftime("%Y-%m-%dT%H:%M")
                    }
                ],
            }
            response = requests.request("POST", f"{base_url}/api/events/", headers=headers, data=json.dumps(data_json))
            # print(response.text)

            r_date = random_date()
            headers["Content_type"] = "application/json"
            data_json = {
                'datetime': (r_date - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "img_url": "http://placeimg.com/1920/1080/any.jpg",
                "name": f"Ceci est un évènement sans artiste",
                "products": products_uuid
            }
            response = requests.request("POST", f"{base_url}/api/events/", headers=headers, data=json.dumps(data_json))