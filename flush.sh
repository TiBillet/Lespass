#!/bin/bash
set -e

if [ "$DEBUG" = "1" ]; then
  export PGPASSWORD=$POSTGRES_PASSWORD
  export PGUSER=$POSTGRES_USER
  export PGHOST=postgres
  dropdb $POSTGRES_DB
  createdb $POSTGRES_DB
  echo "Database reset complete."

#  uv run manage.py migrate
  uv run manage.py migrate_schemas --executor=multiprocessing
  uv run manage.py install

  # Mode light par défaut (1 tenant, 3 events, 2 adhésions).
  # Ajouter --full pour charger toutes les données de démo (5 tenants, initiatives, fédérations).
  uv run manage.py demo_data_v2

  uv run manage.py collectstatic --no-input
#  uv run manage.py create_tenant_superuser --noinput --username root --email root@root.root --schema=public

  echo "start dev server : https://"$SUB"."$DOMAIN"/"
  uv run /DjangoFiles/manage.py runserver 0.0.0.0:8002
else
  echo "DEBUG environment variable is not set"
fi
