python /DjangoFiles/manage.py collectstatic --no-input
python /DjangoFiles/manage.py migrate
echo "Création des tenants public et meta"
python /DjangoFiles/manage.py create_public
echo "Création du super utilisateur"
python /DjangoFiles/manage.py test_user

mkdir -p /DjangoFiles/logs
touch /DjangoFiles/logs/nginxAccess.log
touch /DjangoFiles/logs/nginxError.log
touch /DjangoFiles/logs/gunicorn.logs
touch /DjangoFiles/logs/Djangologfile

sleep infinity
#python /DjangoFiles/manage.py runserver 0.0.0.0:8002
