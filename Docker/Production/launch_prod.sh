#mkdir /root/.ssh
#touch /root/.ssh/known_hosts

#ssh-keyscan aaa.3peaks.re >> /root/.ssh/known_hosts

#crontab /DjangoFiles/cron/cron
#service cron start

mkdir -p /DjangoFiles/www
touch /DjangoFiles/www/nginxAccess.log
touch /DjangoFiles/www/nginxError.log
touch /DjangoFiles/www/gunicorn.logs

cd /DjangoFiles

python manage.py collectstatic --noinput
gunicorn TiBillet.wsgi --log-level=debug --access-logfile /DjangoFiles/www/gunicorn.logs --log-file /DjangoFiles/www/gunicorn.logs --error-logfile /DjangoFiles/www/gunicorn.logs --log-level debug --capture-output --reload -w 5 -b 0.0.0.0:8000
#sleep 2400h
