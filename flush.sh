#!/bin/bash
set -e

if [ "$DEBUG" = "1" ]; then
  export PGPASSWORD=$POSTGRES_PASSWORD
  export PGUSER=$POSTGRES_USER
  export PGHOST=postgres

  # Teste si la table django_migrations existe (= DB deja initialisee)
  # / Check if django_migrations table exists (= DB already initialized)
  TABLE_EXISTS=$(psql -d $POSTGRES_DB -tAc "SELECT to_regclass('public.django_migrations');" 2>/dev/null || echo "")

  if [ "$TABLE_EXISTS" = "django_migrations" ]; then
    # DB deja initialisee : on purge les donnees de demo et on reimporte
    # Pas de drop/recreate, pas de migrations — beaucoup plus rapide
    # / DB already initialized: flush demo data and reimport (no migrations)
    echo "DB existante detectee — flush des donnees de demo sans migrations..."
    poetry run python manage.py demo_data_v2 --flush --no-input
  else
    # Premiere installation ou DB vierge : procedure complete
    # / Fresh install or empty DB: full procedure
    echo "DB vierge detectee — installation complete..."
    dropdb --if-exists $POSTGRES_DB
    createdb $POSTGRES_DB

    poetry run python manage.py migrate_schemas --executor=multiprocessing
    poetry run python manage.py install
    poetry run python manage.py demo_data_v2
  fi

  poetry run python manage.py collectstatic --no-input

  echo "start dev server : https://"$SUB"."$DOMAIN"/"
  poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002
else
  echo "DEBUG environment variable is not set"
fi
