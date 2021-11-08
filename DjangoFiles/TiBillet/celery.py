'''

import os
from celery import Celery

# setting the Django settings module.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')
app = Celery('TiBillet')

app.config_from_object('django.conf:settings', namespace='CELERY')
# Looks up for task modules in Django applications and loads them
app.autodiscover_tasks()


'''

'''
celery -A TiBillet worker -l INFO
from TiBillet.celery import my_task
my_task.delay()
'''

import os
from django.db import connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

from django.conf import settings

from tenant_schemas_celery.app import CeleryApp as TenantAwareCeleryApp

app = TenantAwareCeleryApp()
app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task
def add(x, y):
    return x + y

@app.task
def schema_name():
    return connection.schema_name
