import os, logging
from celery.schedules import crontab
from django.core.management import call_command
from django.utils import timezone

from django.db import connection
from celery.signals import setup_logging
logger = logging.getLogger(__name__)

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



@app.task
def cloture_mensuelle_task():
    """Proxy task pour appeler generer_cloture_mensuelle depuis Celery Beat.
    / Proxy task to call generer_cloture_mensuelle from Celery Beat."""
    from laboutik.tasks import generer_cloture_mensuelle
    generer_cloture_mensuelle()

@app.task
def cloture_annuelle_task():
    """Proxy task pour appeler generer_cloture_annuelle depuis Celery Beat.
    / Proxy task to call generer_cloture_annuelle from Celery Beat."""
    from laboutik.tasks import generer_cloture_annuelle
    generer_cloture_annuelle()


@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # doc : https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html#crontab-schedules
    # Calls test('hello') every 10 seconds.
    # sender.add_periodic_task(10.0, periodic_test.s(f'{timezone.now()} - hello 10'), name='add every 10')
    # sender.add_periodic_task(10.0, cron_morning.s(), name='add every 10')

    # Calls test('hello') every 30 seconds.
    # It uses the same signature of previous task, an explicit name is
    # defined to avoid this task replacing the previous one defined.

    # sender.add_periodic_task(2.0, periodic_test.s(f'{timezone.now()} - hello 30'), name='add every 30')

    # Pour des taches celery qui prennent en compte le tenant, passer une tasks dans un call_command

    # sender.add_periodic_task(30.0, cron_morning.s(), name='test cron')

    logger.info(f'setup_periodic_tasks cron_morning at 5AM UTC')
    sender.add_periodic_task(
        crontab(hour=5, minute=0),
        cron_morning.s(),
    )
    # Cloture mensuelle : le 1er de chaque mois a 3h UTC
    # / Monthly closure: 1st of each month at 3am UTC
    logger.info('setup_periodic_tasks cloture_mensuelle at 3AM UTC, 1st of month')
    sender.add_periodic_task(
        crontab(day_of_month=1, hour=3, minute=0),
        cloture_mensuelle_task.s(),
    )

    # Cloture annuelle : le 1er janvier a 4h UTC
    # / Annual closure: January 1st at 4am UTC
    logger.info('setup_periodic_tasks cloture_annuelle at 4AM UTC, Jan 1st')
    sender.add_periodic_task(
        crontab(month_of_year=1, day_of_month=1, hour=4, minute=0),
        cloture_annuelle_task.s(),
    )

    logger.info(f'setup_periodic_tasks DONE')


@app.task
def periodic_test(arg):
    logger.info(f'{arg} periodic task')
    logger.info(f'{connection.schema_name} schema_name')
    with open('/DjangoFiles/logs/Djangologfile', 'w') as f:
        f.write(f'{arg}\n')
        f.close()

    print(arg)

@app.task
def cron_morning():
    logger.info(f'call_command cron_morning START')
    call_command('cron_morning')
    logger.info(f'call_command cron_morning END')
