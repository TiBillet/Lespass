from django.core.management import call_command
from django.core.management.commands.flush import Command as FlushCommand
from django.db import transaction


class Command(FlushCommand):
    @transaction.atomic
    def handle(self, *args, **options):
        options['allow_cascade'] = True
        call_command('flush', *args, **options)
