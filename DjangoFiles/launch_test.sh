python /DjangoFiles/manage.py collectstatic --no-input
python /DjangoFiles/manage.py migrate
python /DjangoFiles/manage.py create_public
echo "Création du super utilisateur :"
python /DjangoFiles/manage.py create_tenant_superuser -s public --username root --email root@root.root --noinput
python /DjangoFiles/manage.py test_user

mkdir -p /DjangoFiles/logs
touch /DjangoFiles/logs/nginxAccess.log
touch /DjangoFiles/logs/nginxError.log
touch /DjangoFiles/logs/gunicorn.logs
touch /DjangoFiles/logs/Djangologfile

python /DjangoFiles/manage.py runserver 0.0.0.0:8002
