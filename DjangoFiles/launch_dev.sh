set -e
mkdir -p /DjangoFiles/logs
touch /DjangoFiles/logs/nginxAccess.log
touch /DjangoFiles/logs/nginxError.log
touch /DjangoFiles/logs/gunicorn.logs
touch /DjangoFiles/logs/Djangologfile

DB_NAME=$POSTGRES_DB
export PGPASSWORD=$POSTGRES_PASSWORD
export PGUSER=$POSTGRES_USER
export PGHOST=$POSTGRES_HOST
export LOAD_SQL=$LOAD_SQL

load_sql() {
  if psql -lqtA | cut -d\| -f1 | grep -qxF "$DB_NAME"; then
    echo "La base de données ${DB_NAME} existe déjà"
  else
    echo "La base de données ${DB_NAME} n'existe pas"
    sleep 3
    psql --dbname $POSTGRES_DB -f $LOAD_SQL
    echo "SQL file loaded : $LOAD_SQL"
  fi

}

# Fonction qui sera exécutée en cas d'erreur
handle_error() {
  echo "Une erreur s'est produite dans la ligne $1"
  sleep infinity
}

trap 'handle_error $LINENO' ERR
# poetry run python /DjangoFiles/manage.py migrate
# echo "Run rsp pour lancer le serveur web tout neuf"
sleep infinity

#python /DjangoFiles/manage.py runserver 0.0.0.0:8002
