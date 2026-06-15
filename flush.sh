#!/bin/bash
set -e

if [ "$DEBUG" = "1" ]; then
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

  echo "start dev server : https://"$SUB"."$DOMAIN"/"
  poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002
else
  echo "DEBUG environment variable is not set"
fi
