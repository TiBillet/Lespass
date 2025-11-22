#!/bin/bash
set -e

# Se placer dans le dossier du script pour accéder au fichier VERSION
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Charger les variables (VERSION, MIGRATE) depuis le fichier VERSION si disponible
if [[ -f VERSION ]]; then
  # shellcheck disable=SC1091
  source VERSION
fi

#curl -sSL https://install.python-poetry.org | python3
export PATH="/home/tibillet/.local/bin:$PATH"
poetry install
echo "Poetry install ok"

poetry run python /DjangoFiles/manage.py collectstatic --no-input


# Création des tenant publics et agenda
# poetry run python /DjangoFiles/manage.py install

#if [ "$TEST" = "1" ]; then
#  poetry run python manage.py demo_data
#fi

# Migration conditionnelle
if [[ "${MIGRATE:-0}" = "1" ]]; then
  echo "Migrate"
  poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
else
  echo "Skip migrate (MIGRATE=${MIGRATE:-0})"
fi

echo "Gunicorn start"
poetry run gunicorn TiBillet.wsgi --log-level=info --access-logfile /DjangoFiles/logs/gunicorn.logs --log-file /DjangoFiles/logs/gunicorn.logs --error-logfile /DjangoFiles/logs/gunicorn.logs --log-level info --capture-output --reload -w 5 -b 0.0.0.0:8002

