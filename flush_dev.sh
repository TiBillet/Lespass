#!/bin/bash
# flush_dev.sh — Reset complet avec squash des migrations.
# UNIQUEMENT en dev (DEBUG=1). Ne jamais utiliser en prod.
# Resultat : 1 seule migration 0001_initial.py par app, DB neuve, donnees de demo.
set -e

if [ "$DEBUG" != "1" ]; then
  echo "ERREUR : ce script est reservé au dev (DEBUG=1). Abandon."
  exit 1
fi

export PGPASSWORD=$POSTGRES_PASSWORD
export PGUSER=$POSTGRES_USER
export PGHOST=postgres

echo "=== 1/5 — Reset DB ==="
dropdb "$POSTGRES_DB"
createdb "$POSTGRES_DB"

echo "=== 2/5 — Suppression des migrations existantes ==="
APPS=(
  AuthBillet
  BaseBillet
  crowds
  Customers
  discovery
  fedow_connect
  fedow_core
  fedow_public
  MetaBillet
  QrcodeCashless
  root_billet
)
for app in "${APPS[@]}"; do
  dir="/DjangoFiles/${app}/migrations"
  if [ -d "$dir" ]; then
    # Supprime tous les fichiers de migration (garde __init__.py et __pycache__)
    find "$dir" -maxdepth 1 -name "0*.py" -delete
    echo "  $app : migrations supprimees"
  fi
done

echo "=== 3/5 — Generation des nouvelles migrations (1 par app) ==="
poetry run python manage.py makemigrations "${APPS[@]}"

echo "=== 4/5 — Migrations + install + demo ==="
poetry run python manage.py migrate_schemas --executor=multiprocessing
poetry run python manage.py install
poetry run python manage.py demo_data_v2

echo "=== 5/5 — Collectstatic ==="
poetry run python manage.py collectstatic --no-input

echo ""
echo "Termine ! Migrations squashees, DB neuve, donnees de demo chargees."
echo "Demarrage du serveur : https://${SUB}.${DOMAIN}/"
poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002
