import os
from os.path import exists
import requests
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from Customers.models import Client, Domain
import os, json
from django.core.management import call_command


class Command(BaseCommand):

    def handle(self, *args, **options):
        with schema_context('Demo'):
            call_command('flush')

        base_url = "http://demo.django-local.org:8002"
        headers = {}
        email = os.environ.get('EMAIL')
        username = email
        password = 'proutprout123'
        ### Create User :
        print("************ Create User")
        url = f"{base_url}/auth/users/"
        payload = {
            'email': email,
            'password': password,
            'username': username
        }

        response = requests.request("POST", url, data=payload)
        print(response.text)
        with schema_context('Demo'):
            User: TibilletUser = get_user_model()
            admin = User.objects.get(email=email)
            admin.is_active = True
            admin.is_staff = True
            admin.client_admin.add(Client.objects.get(name="Demo"))
            admin.save()

        # assert response.status_code == 200
        print("************ Create User OK")

        ### Get Token user :
        print("************ Create Get Token user")
        url = f"{base_url}/auth/token/login/"
        payload = {'username': email,
                   'password': password}
        response = requests.request("POST", url, data=payload)
        auth_token = response.json().get("auth_token")
        assert auth_token

        headers['Authorization'] = f"Token {auth_token}"
        print("************ Create Get Token user OK")

        ### me :
        print("************ me")

        url = f"{base_url}/auth/users/me/"
        response = requests.request("GET", url, headers=headers, data=payload)

        print(response.text)
        assert response.status_code == 200
        print("************ me OK")

        ### Create product
        print("************ Create Ticket Product")
        url = f"{base_url}/api/products/"
        payload = {'name': 'Billet',
                   'publish': 'true',
                   'categorie_article': 'B'}
        files = [
            ('img', ('tickets_old.png', open('/DjangoFiles/www/demo_img/tickets.png', 'rb'), 'image/png'))
        ]
        response = requests.request("POST", url, headers=headers, data=payload, files=files)
        uuid_ticket_product = response.json().get("uuid")
        print(response.text)
        assert response.status_code == 201
        print("************ Create Ticket Product OK")

        ### Create Ticket prices
        print("************ Create Ticket prices")
        url = f"{base_url}/api/prices/"

        payload = {'name': 'Demi Tarif',
                   'prix': '5',
                   'vat': 'NA',
                   'max_per_user': '10',
                   'stock': '250',
                   'product': uuid_ticket_product}
        response = requests.request("POST", url, headers=headers, data=payload)
        uuid_price_demi = response.json().get("uuid")
        print(response.text)
        assert response.status_code == 201

        payload = {'name': 'Plein Tarif',
                   'prix': '10',
                   'vat': 'NA',
                   'max_per_user': '10',
                   'stock': '250',
                   'product': uuid_ticket_product}
        response = requests.request("POST", url, headers=headers, data=payload)
        uuid_price_plein = response.json().get("uuid")
        print(response.text)
        assert response.status_code == 201
        print("************ Create Ticket prices OK")

        ### Create TShirt product
        print("************ Create TShirt Product")
        url = f"{base_url}/api/products/"
        payload = {'name': 'TShirt',
                   'publish': 'true',
                   'categorie_article': 'T'}
        files = [
            ('img', ('tshirt.png', open('/DjangoFiles/www/demo_img/tshirt.png', 'rb'), 'image/png'))
        ]
        response = requests.request("POST", url, headers=headers, data=payload, files=files)
        uuid_tshirt_product = response.json().get("uuid")
        print(response.text)
        assert response.status_code == 201
        print("************ Create TShirt Product OK")

        ### Create Ticket prices
        print("************ Create TShirt prices")
        url = f"{base_url}/api/prices/"

        payload = {'name': 'S',
                   'prix': '5',
                   'vat': 'NA',
                   'max_per_user': '10',
                   'stock': '250',
                   'product': uuid_tshirt_product}
        response = requests.request("POST", url, headers=headers, data=payload)
        uuid_tshirt_s = response.json().get("uuid")
        print(response.text)
        assert response.status_code == 201

        payload = {'name': 'L',
                   'prix': '5',
                   'vat': 'NA',
                   'max_per_user': '10',
                   'stock': '250',
                   'product': uuid_tshirt_product}
        response = requests.request("POST", url, headers=headers, data=payload)
        uuid_tshirt_l = response.json().get("uuid")
        print(response.text)
        assert response.status_code == 201
        print("************ Create TShirt prices OK")

        ### Create Event
        print("************ Create Event prices")
        url = f"{base_url}/api/events/"

        payload = {'name': 'Ziskakan',
                   'datetime': '2023-10-01T10:20',
                   'short_description': 'Fête ses 40ans',
                   'long_description': 'Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum Lorem Ispum ',
                   'products': [uuid_tshirt_product, uuid_ticket_product],
                   'event_facebook_url': 'https://www.facebook.com/events/2251615698313858'}
        files = [
            ('img', ('Ziskakan.jpg', open('/DjangoFiles/www/demo_img/Ziskakan.jpg', 'rb'), 'image/jpeg'))
        ]

        response = requests.request("POST", url, headers=headers, data=payload, files=files)
        print(response.text)
