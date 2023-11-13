from os.path import exists

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from Customers.models import Client
from QrcodeCashless.models import Detail, CarteCashless
from django.core.validators import URLValidator

import csv, uuid

"""
Methode manuelle :
depuis cashless :
[[str(c.pk),str(c.uuid_qrcode),c.number,c.tag_id] for c in CarteCashless.objects.all()]
copier et coller dans un dic sur billetterie
for c in cartes:
    CarteCashless.objects.get_or_create(
                                uuid=c[1],
                                number=c[2],
                                tag_id=c[3],
                                detail=origin,
                            )
"""

class Command(BaseCommand):

    def is_string_an_url(self, url_string):
        validate_url = URLValidator()

        try:
            validate_url(url_string)
        except ValidationError as e:
            return False
        return True

    def add_arguments(self, parser):

        # Named (optional) arguments
        parser.add_argument(
            '--demo',
            action='store_true',
            help='pop demo cards',
        )

    def handle(self, *args, **options):
        try:
            from data.csv.loader import get_detail_cards
            all_cards_dict = get_detail_cards(demo=options.get('demo'))
        except Exception as e:
            print(f'data.csv.loader or csv file not found : {e}')
            raise e

        for detail in all_cards_dict:
            generation = detail['generation']
            tenant = detail['tenant']
            slug = slugify(f"{tenant.lower()}-{generation}")

            client_tenant = None
            try :
                client_tenant = Client.objects.get(schema_name=tenant.lower())
            except Client.DoesNotExist:
                pass
            except Exception as e:
                print(e)
                raise e

            part = detail['cards'][0][0].partition('/qr/')
            base_url = f"{part[0]}{part[1]}"

            if self.is_string_an_url(base_url) :
                detail_carte, created = Detail.objects.get_or_create(
                    base_url=base_url,
                    origine=client_tenant,
                    generation=generation,
                    slug=slug,
                )

                numline = 1
                all_line = len(detail['cards'])
                for card in detail['cards']:
                    url = card[0]
                    numbers = card[1]
                    tag_id = card[2]

                    # On vérifie que le qrcode soit bien un uuid
                    part = url.partition('/qr/')
                    uuid_url = uuid.UUID(part[2])

                    try :
                        carte, created = CarteCashless.objects.get_or_create(
                            uuid=uuid_url,
                            number=numbers,
                            tag_id=tag_id,
                            detail=detail_carte,
                        )

                        numline += 1
                        print(f"{slug} : {numline}/{all_line} : {carte} created : {created}")
                    except Exception as e:
                        print(e)
                        import ipdb; ipdb.set_trace()
