poetry run python /DjangoFiles/manage.py collectstatic --no-input
poetry run python /DjangoFiles/manage.py migrate
poetry run python /DjangoFiles/manage.py create_public
echo "Création du super utilisateur :"
poetry run python /DjangoFiles/manage.py create_tenant_superuser -s public