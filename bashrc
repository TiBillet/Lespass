# only for convenient :)

alias mm="uv /DjangoFiles/manage.py migrate"
alias sp="uv run manage.py tenant_command shell_plus --print-sql"

alias rsp="uv run /DjangoFiles/manage.py runserver 0.0.0.0:8002 2>&1 | tee /DjangoFiles/runserver.log"

alias guni="uv run /DjangoFiles/manage.py collectstatic --no-input && uv run gunicorn TiBillet.wsgi --capture-output --reload -w 3 -b 0.0.0.0:8002 2>&1 | tee /DjangoFiles/runserver.log"

alias cel="uv run celery -A TiBillet worker -l INFO"

alias test="uv run /DjangoFiles/manage.py test"

alias mmes="uv run manage.py makemessages -l en && uv run manage.py  makemessages -l fr"
alias cmes="uv run manage.py compilemessages"

alias pshell="source .venv/bin/activate"

tibinstall() {
    uv run /DjangoFiles/manage.py collectstatic
    uv run /DjangoFiles/manage.py migrate
    uv run /DjangoFiles/manage.py create_public
    echo "Création du super utilisateur :"
    uv run /DjangoFiles/manage.py create_tenant_superuser -s public
}

load_sql() {
    export PGPASSWORD=$POSTGRES_PASSWORD
    export PGUSER=$POSTGRES_USER
    export PGHOST=postgres
    psql --dbname $POSTGRES_DB -f $1
}