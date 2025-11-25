#!/bin/bash
set -e

if [ "$TEST" = "1" ]; then
  export PGPASSWORD=$POSTGRES_PASSWORD
  export PGUSER=$POSTGRES_USER
  export PGHOST=postgres
  dropdb $POSTGRES_DB
  createdb $POSTGRES_DB
  echo "Database reset complete."

#  poetry run python manage.py migrate
  poetry run python manage.py migrate_schemas --executor=multiprocessing
  poetry run python manage.py install

  poetry run python manage.py demo_data_v2
#  poetry run python manage.py demo_data

  poetry run python manage.py collectstatic --no-input
#  poetry run python manage.py create_tenant_superuser --noinput --username root --email root@root.root --schema=public

  echo "start dev server : https://"$SUB"."$DOMAIN"/"
  poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002
else
  echo "TEST environment variable is not set"
fi
