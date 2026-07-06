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
# Peut être qu'on pourra utilise ./manage.py showmigrations | grep '\[ \]' a terme ?
if [[ "${MIGRATE:-0}" = "1" ]]; then
  echo "Migrate"
  poetry run python /DjangoFiles/manage.py migrate_schemas --executor=multiprocessing
else
  echo "Skip migrate (MIGRATE=${MIGRATE:-0})"
fi

# Dossiers de logs pour supervisord et ses programmes
# / Log folders for supervisord and its programs
mkdir -p /DjangoFiles/logs/supervisor
touch /DjangoFiles/logs/gunicorn.logs /DjangoFiles/logs/daphne.logs /DjangoFiles/logs/celery.logs

# Supervisord orchestre les 3 processus du conteneur :
# - gunicorn : HTTP (port 8002)
# - daphne   : WebSockets (port 7999) — ws/laboutik, ws/printer, ws/rfid...
# - celery   : worker + beat (remplace l'ancien conteneur lespass_celery)
# Gestion : poetry run supervisorctl status|restart gunicorn|daphne|celery
# / Supervisord orchestrates the container's 3 processes:
# gunicorn (HTTP :8002), daphne (WebSockets :7999), celery (worker + beat).
echo "Supervisord start (gunicorn + daphne + celery)"
/usr/bin/supervisord -c /DjangoFiles/supervisor/supervisord.conf &

# Laisse supervisord démarrer puis suit tous les logs (sortie du conteneur).
# Ctrl+C sur le tail n'arrête PAS les services.
# / Give supervisord a moment then tail all logs (container output).
sleep 2
exec tail -f /DjangoFiles/logs/gunicorn.logs /DjangoFiles/logs/daphne.logs /DjangoFiles/logs/celery.logs /DjangoFiles/logs/supervisor/supervisord.log

# Pour relancer les workers gunicorn à chaud :
# supervisorctl -c /DjangoFiles/supervisor/supervisord.conf restart gunicorn
# ou : pkill -HUP -f "gunicorn TiBillet.wsgi"
