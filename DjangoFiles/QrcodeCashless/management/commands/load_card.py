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

        input_generation = input('quelle génération ? \n')
        print(' ')

        print('url, numéro imprimé len(8), fisrt tag id len(8)')
        input_fichier_csv = input('path fichier csv ? \n')
        file = open(input_fichier_csv)

        # file = open('data/raffinerie_1_RETOUR_USINE.csv')


        csv_parser = csv.reader(file)
        list_csv = []
        for line in csv_parser:
            list_csv.append(line)

        # on saucissonne l'url d'une ligne au pif :
        part = list_csv[10][0].partition('/qr/')
        base_url = f"{part[0]}{part[1]}"
        if self.is_string_an_url(base_url) :
            detail_carte, created = Detail.objects.get_or_create(
                base_url=base_url,
                origine=client_tenant,
                generation=input_generation,
            )

            numline = 1
            for line in list_csv:
                print(numline)
                part = line[0].partition('/qr/')
                try:
                    uuid_url = uuid.UUID(part[2])
                    print(f"uuid_url : {uuid_url}")
                    print(f"number : {line[1]}")
                    print(f"tag_id : {line[2]}")
                    if str(uuid_url).partition('-')[0].upper() != line[1]:
                        print('ERROR PRINT != uuid')
                        break


                    carte, created = CarteCashless.objects.get_or_create(
                        tag_id=line[2],
                        uuid=uuid_url,
                        number=line[1],
                        detail=detail_carte,
                    )

                    numline += 1
                except:
                    pass

