poetry run python /DjangoFiles/manage.py collectstatic --no-input
poetry run python /DjangoFiles/manage.py migrate
echo "Création des tenants public et meta"
poetry run python /DjangoFiles/manage.py create_public
echo "Création du super utilisateur"
poetry run python /DjangoFiles/manage.py test_user

mkdir -p /DjangoFiles/logs
touch /DjangoFiles/logs/nginxAccess.log
touch /DjangoFiles/logs/nginxError.log
touch /DjangoFiles/logs/gunicorn.logs
touch /DjangoFiles/logs/Djangologfile

poetry run python /DjangoFiles/manage.py runserver 0.0.0.0:8002
