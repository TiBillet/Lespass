set -e
mkdir -p /DjangoFiles/logs
touch /DjangoFiles/logs/nginxAccess.log
touch /DjangoFiles/logs/nginxError.log
touch /DjangoFiles/logs/gunicorn.logs
touch /DjangoFiles/logs/Djangologfile

python /DjangoFiles/manage.py collectstatic --noinput

export PGPASSWORD=$POSTGRES_PASSWORD
export PGUSER=$POSTGRES_USER
export PGHOST=$POSTGRES_HOST

export LOAD_SQL=$LOAD_SQL
psql --dbname $POSTGRES_DB -f $LOAD_SQL

echo "SQL file loaded : $LOAD_SQL"
python /DjangoFiles/manage.py migrate
echo "Run rsp pour lancer le serveur web tout neuf"
sleep infinity
#python /DjangoFiles/manage.py runserver 0.0.0.0:8002
