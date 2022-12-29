from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from AuthBillet.models import TibilletUser


class Command(BaseCommand):


    def handle(self, *args, **options):
        User = get_user_model()
        root : TibilletUser = User.objects.get(email="root@root.root")
        root.set_password('root')
        root.save()