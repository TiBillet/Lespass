from django.contrib.auth.models import Permission, Group
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import BaseCommand

from BaseBillet.models import OptionGenerale, Configuration


def show_permission_of_model(model):
    content_type = ContentType.objects.get_for_model(model)
    p = Permission.objects.filter(
        content_type=content_type,
    )
    for x in p:
        print(x.codename)


class Command(BaseCommand):


    def handle(self, *args, **options):

        liste_permission_user_staff = [

            "change_configuration",
            "view_configuration",

            "add_optiongenerale",
            "change_optiongenerale",
            "delete_optiongenerale",
            "view_optiongenerale",

            "add_product",
            "change_product",
            "delete_product",
            "view_product",

            "add_price",
            "change_price",
            "delete_price",
            "view_price",

            "add_event",
            "change_event",
            "delete_event",
            "view_event",

            "view_paiement_stripe",

            "change_reservation",
            "delete_reservation",
            "view_reservation",

            "add_membership",
            "change_membership",
            "delete_membership",
            "view_membership",

            "add_apikey",
            "change_apikey",
            "delete_apikey",
            "view_apikey",

            "add_externalapikey",
            "change_externalapikey",
            "delete_externalapikey",
            "view_externalapikey",

            "add_webhook",
            "change_webhook",
            "delete_webhook",
            "view_webhook",

        ]


        # on clean les anciennes permissions:
        Permission.objects.all().delete()
        call_command('update_permissions')

        staff_group = Group.objects.get_or_create(name="staff")[0]
        for permission in liste_permission_user_staff:
            print(permission)
            perm = Permission.objects.get(codename=permission)
            print(perm)

            staff_group.permissions.add(perm)
        staff_group.save()