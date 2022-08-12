from os.path import exists

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from Customers.models import Client
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
        cards_dict = {}
        input_file_find = False
        if exists("/DjangoFiles/data/domains_and_cards_betabillet.py"):
            print("/DjangoFiles/data/domains_and_cards_betabillet.py existe. On charge depuis ce fichier ?")
            input_file_find = input('Y ? \n')

        if input_file_find == "Y":
            from data.domains_and_cards_betabillet import cards
            cards_dict = cards
        else :
            for client in Client.objects.all():
                print (client.schema_name)

            input_client = input('quel client ? \n')

            cards_dict[input_client]= {}
            print(' ')
            # client_tenant = Client.objects.get(schema_name='VavangArt')

            input_generation = input('quelle génération ? \n')

            print(' ')

            input_fichier_csv = input('path fichier csv ? \n')
            cards_dict[input_client][input_generation]=input_fichier_csv

        # file = open('/DjangoFiles/data/csv/Vavangart_G1.csv')

        for client, gens in cards_dict.items():
            print(client, gens)
            client_tenant = Client.objects.get(schema_name=client.lower())
            print(client)
            for gen, file in gens.items():
                print(gen,file)
                file = open(file)

                csv_parser = csv.reader(file)
                list_csv = []
                for line in csv_parser:
                    list_csv.append(line)

                # import ipdb; ipdb.set_trace()
                # on saucissonne l'url d'une ligne au pif :
                part = list_csv[10][0].partition('/qr/')
                base_url = f"{part[0]}{part[1]}"



                if self.is_string_an_url(base_url) :
                    detail_carte, created = Detail.objects.get_or_create(
                        base_url=base_url,
                        origine=client_tenant,
                        generation=gen,
                    )

                    numline = 1
                    for line in list_csv:
                        print(numline)
                        part = line[0].partition('/qr/')
                        try:
                            uuid_url = uuid.UUID(part[2])
                            print(f"base_url : {base_url}")
                            print(f"uuid_url : {uuid_url}")
                            print(f"number : {line[1]}")
                            print(f"tag_id : {line[2]}")
                            # if str(uuid_url).partition('-')[0].upper() != line[1]:
                            #     print('ERROR PRINT != uuid')
                            #     break


                            carte, created = CarteCashless.objects.get_or_create(
                                tag_id=line[2],
                                uuid=uuid_url,
                                number=line[1],
                                detail=detail_carte,
                            )

                            numline += 1
                        except:
                            pass

