import os
from django.db import connection
from celery.signals import setup_logging
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

from django.conf import settings

from tenant_schemas_celery.app import CeleryApp as TenantAwareCeleryApp

app = TenantAwareCeleryApp()
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

@setup_logging.connect
def config_loggers(*args, **kwags):
    from logging.config import dictConfig
    from django.conf import settings
    dictConfig(settings.LOGGING)

@app.task
def add(x, y):
    return x + y

@app.task
def schema_name():
    return connection.schema_name
