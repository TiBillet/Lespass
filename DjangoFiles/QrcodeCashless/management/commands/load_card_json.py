import json
import os

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from Customers.models import Client, Domain
from QrcodeCashless.models import Detail, CarteCashless
from django.core.validators import URLValidator

import csv, uuid




class Command(BaseCommand):

    def is_string_an_url(self, url_string):
        validate_url = URLValidator()

        try:
            validate_url(url_string)
        except ValidationError as e:
            return False
        return True


    def handle(self, *args, **options):
        for client in Client.objects.all():
            print (client.schema_name)

        input_client = input('quel client ? \n')
        client_tenant = Client.objects.get(schema_name=input_client)
        print(' ')
        print('url, numéro imprimé len(8), fisrt tag id len(8)')

        input_generation = input('quelle génération ? \n')
        print(' ')

        detail_carte, created = Detail.objects.get_or_create(
            base_url='https://m.tibillet.re/',
            origine=client_tenant,
            generation=input_generation,
        )

        file = open('data/CarteCashlessBisik.json')
        json_dict = json.load(file)

        for card in json_dict:
            tag_id = card['fields']['tag_id']
            number = card['fields']['number']
            if tag_id and number:
                # on va generer un faux uuid pour le bisik
                # Namespace hardcodé volontairement pour vérification
                namespace = uuid.UUID('6ba7b811-9dad-11d1-80b4-00c04fd430c8')
                gen_uuid = uuid.uuid5(namespace, number)

                print(tag_id)
                print(number)
                print(gen_uuid)

                carte, created = CarteCashless.objects.get_or_create(
                    tag_id=tag_id,
                    uuid=gen_uuid,
                    number=number,
                    detail=detail_carte,
                )


