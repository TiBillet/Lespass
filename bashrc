# only for convenient :)

alias mm="poetry run python /DjangoFiles/manage.py migrate"
alias sp="poetry run python manage.py tenant_command shell_plus"

alias rsp="poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002"
alias guni="poetry run gunicorn TiBillet.wsgi --capture-output --reload -w 3 -b 0.0.0.0:8002"

alias cel="poetry run celery -A TiBillet worker -l INFO"

alias test="poetry run python /DjangoFiles/manage.py test"

alias mmes="poetry run django-admin makemessages -l en && django-admin makemessages -l fr"
alias cmes="poetry run django-admin compilemessages"

alias pshell="eval $(poetry env activate)"

tibinstall() {
    poetry run python /DjangoFiles/manage.py collectstatic
    poetry run python /DjangoFiles/manage.py migrate
    poetry run python /DjangoFiles/manage.py create_public
    echo "Création du super utilisateur :"
    poetry run python /DjangoFiles/manage.py create_tenant_superuser -s public
}

load_sql() {
    export PGPASSWORD=$POSTGRES_PASSWORD
    export PGUSER=$POSTGRES_USER
    export PGHOST=postgres
    psql --dbname $POSTGRES_DB -f $1
}