#!/bin/bash
set -e

# Si le conteneur tourne sous supervisord (prod/pre-prod : gunicorn + daphne
# + celery), on arrête les services le temps du flush : sinon leurs
# connexions PostgreSQL font échouer dropdb, et le runserver final entrerait
# en collision avec gunicorn (port 8002).
# / If the container runs under supervisord (prod/pre-prod: gunicorn +
# daphne + celery), stop the services during the flush: their PostgreSQL
# connections would make dropdb fail, and the final runserver would clash
# with gunicorn (port 8002).
SUPERVISOR_CONF=/DjangoFiles/supervisor/supervisord.conf
SUPERVISOR_SOCK=/DjangoFiles/logs/supervisor/supervisor.sock

if [ "$DEBUG" = "1" ]; then
  if [ -S "$SUPERVISOR_SOCK" ]; then
    echo "Supervisord détecté : arrêt des services le temps du flush."
    supervisorctl -c $SUPERVISOR_CONF stop all
  fi

  export PGPASSWORD=$POSTGRES_PASSWORD
  export PGUSER=$POSTGRES_USER
  export PGHOST=postgres
  dropdb $POSTGRES_DB
  createdb $POSTGRES_DB
  echo "Database reset complete."

#  poetry run python manage.py migrate
  poetry run python manage.py migrate_schemas --executor=multiprocessing
  poetry run python manage.py install

  # Mode light par défaut (1 tenant, 3 events, 2 adhésions).
  # Ajouter --full pour charger toutes les données de démo (5 tenants, initiatives, fédérations).
  poetry run python manage.py demo_data_v2

  poetry run python manage.py collectstatic --no-input
#  poetry run python manage.py create_tenant_superuser --noinput --username root --email root@root.root --schema=public

  # Rafraichit le cache SEO (landing root : lieux, evenements, sitemap).
  # Sans cet appel, la landing affiche "0 lieux" tant que Celery beat n'a
  # pas tourne (toutes les 4h).
  # / Refresh SEO cache (root landing: venues, events, sitemap).
  # Without this call, the landing shows "0 lieux" until Celery beat fires
  # (every 4h).
  poetry run python manage.py refresh_seo_cache

  if [ -S "$SUPERVISOR_SOCK" ]; then
    # Relance gunicorn + daphne + celery / Restart gunicorn + daphne + celery
    supervisorctl -c $SUPERVISOR_CONF start all
    echo "Services relancés : https://"$SUB"."$DOMAIN"/"
  else
    echo "start dev server : https://"$SUB"."$DOMAIN"/"
    poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002
  fi
else
  echo "DEBUG environment variable is not set"
fi
