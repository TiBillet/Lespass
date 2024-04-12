#!/bin/bash
set -e

#curl -sSL https://install.python-poetry.org | python3
export PATH="/home/tibillet/.local/bin:$PATH"
poetry install
echo "Poetry install ok"

poetry run python /DjangoFiles/manage.py collectstatic --no-input
poetry run python /DjangoFiles/manage.py migrate

# Création des tenant publics et agenda
poetry run python /DjangoFiles/manage.py create_public
# Handshake fedow
poetry run python /DjangoFiles/manage.py root_fedow

gunicorn TiBillet.wsgi --log-level=info --access-logfile /DjangoFiles/logs/gunicorn.logs --log-file /DjangoFiles/logs/gunicorn.logs --error-logfile /DjangoFiles/logs/gunicorn.logs --log-level info --capture-output --reload -w 5 -b 0.0.0.0:8000

