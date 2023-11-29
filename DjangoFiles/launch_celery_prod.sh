set -e
#celery flower --port=5566
poetry run celery -A TiBillet worker -l INFO
