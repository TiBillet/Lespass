#touch /root/.ssh/known_hosts

#ssh-keyscan aaa.3peaks.re >> /root/.ssh/known_hosts

#crontab /DjangoFiles/cron/cron
#service cron start

mkdir -p /DjangoFiles/logs
touch /DjangoFiles/logs/nginxAccess.log
touch /DjangoFiles/logs/nginxError.log
touch /DjangoFiles/logs/gunicorn.logs
touch /DjangoFiles/logs/Djangologfile

cd /DjangoFiles

python manage.py collectstatic --noinput
gunicorn TiBillet.wsgi --log-level=debug --access-logfile /DjangoFiles/logs/gunicorn.logs --log-file /DjangoFiles/logs/gunicorn.logs --error-logfile /DjangoFiles/logs/gunicorn.logs --log-level debug --capture-output --reload -w 5 -b 0.0.0.0:8000
#sleep 2400h
