set -e
mkdir -p /DjangoFiles/logs

# check id
id

touch /DjangoFiles/logs/nginxAccess.log
touch /DjangoFiles/logs/nginxError.log
touch /DjangoFiles/logs/gunicorn.logs
touch /DjangoFiles/logs/Djangologfile

echo "dev mode : sleep infinity"
echo "To start the server : rsp"
sleep infinity
#poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002
