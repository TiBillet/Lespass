#!/bin/bash
set -e

if [ "$TEST" = "1" ]; then
  export PGPASSWORD=$POSTGRES_PASSWORD
  export PGUSER=$POSTGRES_USER
  export PGHOST=$POSTGRES_HOST
  dropdb $POSTGRES_DB
  createdb $POSTGRES_DB
  echo "Database reset complete."

  poetry run ./manage.py migrate
  poetry run ./manage.py install --tdd
  poetry run ./manage.py create_tenant_superuser --noinput --username root --email root@root.root --schema=public

  echo "start dev server : https://"$SUB"."$DOMAIN"/"
  poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002
else
  echo "TEST environment variable is not set"
fi
