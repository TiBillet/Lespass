set -e
mkdir -p /DjangoFiles/logs
touch /DjangoFiles/logs/nginxAccess.log
touch /DjangoFiles/logs/nginxError.log
touch /DjangoFiles/logs/gunicorn.logs
touch /DjangoFiles/logs/Djangologfile

python /DjangoFiles/manage.py migrate
sleep infinity
#python /DjangoFiles/manage.py runserver 0.0.0.0:8002
