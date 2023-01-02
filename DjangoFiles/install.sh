python /DjangoFiles/manage.py collectstatic --no-input
python /DjangoFiles/manage.py migrate
python /DjangoFiles/manage.py create_public
echo "Création du super utilisateur :"
python /DjangoFiles/manage.py create_tenant_superuser -s public