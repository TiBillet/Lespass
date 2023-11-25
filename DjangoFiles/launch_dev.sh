set -e
mkdir -p /DjangoFiles/logs
touch /DjangoFiles/logs/nginxAccess.log
touch /DjangoFiles/logs/nginxError.log
touch /DjangoFiles/logs/gunicorn.logs
touch /DjangoFiles/logs/Djangologfile

#sleep infinity

DB_NAME=$POSTGRES_DB
#if psql -lqtA | cut -d\| -f1 | grep -qxF "$DB_NAME"; then
#  echo "La base de données ${DB_NAME} existe déjà"
#else
#  echo "La base de données ${DB_NAME} n'existe pas"
##  pg_restore -f $LOAD_SQL
#  export PGPASSWORD=$POSTGRES_PASSWORD
#  export PGUSER=$POSTGRES_USER
#  export PGHOST=$POSTGRES_HOST
#  export LOAD_SQL=$LOAD_SQL
#  psql --dbname $POSTGRES_DB -f $LOAD_SQL
#  echo "SQL file loaded : $LOAD_SQL"
#fi


# poetry run python /DjangoFiles/manage.py collectstatic --noinput
poetry run python /DjangoFiles/manage.py migrate
sleep infinity

echo "Run rsp pour lancer le serveur web tout neuf"
#python /DjangoFiles/manage.py runserver 0.0.0.0:8002


# Passage de postgres 13 a 14 :
# Passer la version de postgres à 13-alpine
# echo $POSTGRES_PASSWORD
# export && psql --dbname $POSTGRES_DB
# \password
# retourner sur le conteneur et lancer le backup