set -e
sleep infinity
#celery flower --port=5566
poetry update
poetry run celery -A TiBillet worker -l INFO
