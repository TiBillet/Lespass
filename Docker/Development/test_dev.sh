#!/usr/bin/env bash
docker compose down --remove-orphans
sudo rm -rf ../../Postgres/dbdata

#docker compose pull
docker compose up -d
sleep 5

docker compose exec billetterie_django_dev python /DjangoFiles/manage.py collectstatic --noinput
docker compose exec billetterie_django_dev python /DjangoFiles/manage.py migrate
docker compose exec billetterie_django_dev python /DjangoFiles/manage.py create_public
echo "Création du super utilisateur :"
docker compose exec billetterie_django_dev python /DjangoFiles/manage.py create_tenant_superuser -s public --username root --email root@root.root --noinput
docker compose exec billetterie_django_dev python /DjangoFiles/manage.py test_user
docker compose exec billetterie_django_dev bash

