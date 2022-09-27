import uuid
from os.path import exists

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django_tenants.utils import tenant_context

from BaseBillet.models import Configuration
from Customers.models import Client, Domain
import os

from QrcodeCashless.models import CarteCashless, Detail


class Command(BaseCommand):

    def handle(self, *args, **options):

        def config_billetistan():
            billetistan = Client.objects.get(schema_name="billetistan")
            with tenant_context(billetistan):
                config = Configuration.get_solo()
                config.stripe_mode_test = True
                config.server_cashless = "http://172.17.0.1:8001"
                config.save()

        def add_cards():
            cards = [
                ["https://billetistan.django-local.org/qr/76dc433c-00ac-479c-93c4-b7a0710246af", "76DC433C", "EE144CE8"],
                ["https://billetistan.django-local.org/qr/87683c94-1187-49ae-a64d-54174f6eb76d", "87683C94", "93BD3684"],
                ["https://billetistan.django-local.org/qr/c2b2400c-1f7e-4305-b75e-8c1db3f8d113", "C2B2400C", "41726643"],
                ["https://billetistan.django-local.org/qr/7c9b0d8a-6c37-433b-a091-2c6017b085f0", "7C9B0D8A", "11372ACA"],
                ["https://billetistan.django-local.org/qr/8ee38b17-fc02-4c8d-84cb-59eaaa059ee0", "8EE38B17", "01F81FCB"],
                ["https://billetistan.django-local.org/qr/f75234fc-0c86-40cf-ae00-604cd3719403", "F75234FC", "CC3EB41E"],
                ["https://billetistan.django-local.org/qr/b2eba074-f070-4fe3-9150-deda224b708d", "B2EBA074", "91168FE9"],
                ["https://billetistan.django-local.org/qr/5ddb4c9f-5f9e-4fa1-aacb-60316f2a3aea", "5DDB4C9F", "A14F75E9"],
                ["https://billetistan.django-local.org/qr/189ce45e-d606-4e5a-bfbe-5ed5ec5e4995", "189CE45E", "A14DD6CA"],
                ["https://billetistan.django-local.org/qr/d6cad253-b6cf-4d8f-9238-0927de8a4ce9", "D6CAD253", "01F097CA"],
                ["https://billetistan.django-local.org/qr/eced8aef-3e1f-4614-be11-b756768c9bad", "ECED8AEF", "4172AACA"],
                ["https://billetistan.django-local.org/qr/7dc2fee6-a312-4ff3-849c-b26da9302174", "7DC2FEE6", "F18923CB"],
            ]

            client_tenant = Client.objects.get(schema_name="billetistan")

            for card in cards :
                part = card[0].partition('/qr/')
                base_url = f"{part[0]}{part[1]}"
                uuid_url = uuid.UUID(part[2])
                number = card[1]
                tag_id = card[2]

                detail_carte, created = Detail.objects.get_or_create(
                    base_url=base_url,
                    origine=client_tenant,
                    generation=66,
                )

                carte, created = CarteCashless.objects.get_or_create(
                    tag_id=tag_id,
                    uuid=uuid_url,
                    number=number,
                    detail=detail_carte,
                )
                print(carte.tag_id, created)


        config_billetistan()
        add_cards()