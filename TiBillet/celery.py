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

    # Rafraichissement du cache SEO cross-tenant toutes les 4 heures.
    # On passe par un wrapper @app.task local (pattern cron_morning) pour
    # eviter la race entre on_after_configure et autodiscover_tasks.
    # / Cross-tenant SEO cache refresh every 4 hours.
    # We go through a local @app.task wrapper (cron_morning pattern) to
    # avoid the on_after_configure vs autodiscover_tasks race.
    # cf. seo/tasks.py + TECH DOC/SESSIONS/M-To-V2/02-app-seo.md
    logger.info(f'setup_periodic_tasks cron_refresh_seo_cache every 4 hours')
    sender.add_periodic_task(
        crontab(minute=0, hour='*/4'),
        cron_refresh_seo_cache.s(),
    )

    # Purge hebdomadaire des brouillons d'onboarding non finalises
    # (Lundi 3h UTC). On passe par un wrapper @app.task local pour eviter
    # la race entre on_after_configure et autodiscover_tasks (meme pattern
    # que cron_refresh_seo_cache).
    # / Weekly cleanup of unfinalized onboarding drafts (Monday 3am UTC).
    # We go through a local @app.task wrapper to avoid the
    # on_after_configure vs autodiscover_tasks race (same pattern as
    # cron_refresh_seo_cache).
    # cf. onboard/tasks.py::purge_stale_onboard_drafts
    logger.info(f'setup_periodic_tasks cron_purge_stale_onboard_drafts at Monday 3AM UTC')
    sender.add_periodic_task(
        crontab(day_of_week=1, hour=3, minute=0),
        cron_purge_stale_onboard_drafts.s(),
    )

    # Clotures comptables periodiques (cf. comptabilite/tasks.py)
    # / Periodic accounting closures
    logger.info(f"setup_periodic_tasks cron_cloture_quotidienne at 6:00 UTC")
    sender.add_periodic_task(
        crontab(hour=6, minute=0),
        cron_cloture_quotidienne.s(),
        name="cron_cloture_quotidienne",
    )
    sender.add_periodic_task(
        crontab(day_of_week=1, hour=6, minute=15),
        cron_cloture_hebdomadaire.s(),
        name="cron_cloture_hebdomadaire",
    )
    sender.add_periodic_task(
        crontab(day_of_month=1, hour=6, minute=30),
        cron_cloture_mensuelle.s(),
        name="cron_cloture_mensuelle",
    )
    sender.add_periodic_task(
        crontab(month_of_year=1, day_of_month=1, hour=6, minute=45),
        cron_cloture_annuelle.s(),
        name="cron_cloture_annuelle",
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


@app.task
def cron_refresh_seo_cache():
    """
    Wrapper local pour la task seo. On passe par call_command pour
    benificier de l'enregistrement automatique au niveau de l'app Celery.
    / Local wrapper for the seo task. Goes through call_command to
    benefit from automatic registration at the Celery app level.
    """
    logger.info(f'call_command refresh_seo_cache START')
    call_command('refresh_seo_cache')
    logger.info(f'call_command refresh_seo_cache END')


@app.task
def cron_purge_stale_onboard_drafts():
    """
    Wrapper local pour la task purge_stale_onboard_drafts (app onboard).
    On passe par un wrapper @app.task local pour eviter la race entre
    on_after_configure et autodiscover_tasks (meme pattern que
    cron_refresh_seo_cache).
    / Local wrapper for purge_stale_onboard_drafts (onboard app).
    Local @app.task wrapper avoids the on_after_configure vs
    autodiscover_tasks race (same pattern as cron_refresh_seo_cache).
    """
    # Import local pour eviter de tirer onboard.tasks au chargement du module
    # celery (qui est tres precoce dans le boot Django).
    # / Local import to avoid pulling onboard.tasks at celery module load
    # time (very early in Django boot).
    from onboard.tasks import purge_stale_onboard_drafts
    logger.info(f'purge_stale_onboard_drafts START')
    deleted = purge_stale_onboard_drafts()
    logger.info(f'purge_stale_onboard_drafts END (deleted={deleted})')


@app.task
def cron_cloture_quotidienne():
    """
    Genere les clotures comptables quotidiennes (niveau J).
    / Generates daily accounting closures (J level).
    """
    logger.info(f"call_command generer_cloture --niveau=J START")
    call_command("generer_cloture", "--niveau=J")
    logger.info(f"call_command generer_cloture --niveau=J END")


@app.task
def cron_cloture_hebdomadaire():
    """Wrapper hebdomadaire (lundi 6h15 UTC)."""
    logger.info(f"call_command generer_cloture --niveau=H START")
    call_command("generer_cloture", "--niveau=H")
    logger.info(f"call_command generer_cloture --niveau=H END")


@app.task
def cron_cloture_mensuelle():
    """Wrapper mensuel (1er du mois 6h30 UTC)."""
    logger.info(f"call_command generer_cloture --niveau=M START")
    call_command("generer_cloture", "--niveau=M")
    logger.info(f"call_command generer_cloture --niveau=M END")


@app.task
def cron_cloture_annuelle():
    """Wrapper annuel (1er janvier 6h45 UTC)."""
    logger.info(f"call_command generer_cloture --niveau=A START")
    call_command("generer_cloture", "--niveau=A")
    logger.info(f"call_command generer_cloture --niveau=A END")
