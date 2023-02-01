#sleep 34d
#celery flower --port=5566
celery -A TiBillet worker -l INFO
