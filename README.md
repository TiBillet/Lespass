# TiBillet-Ticket

Réseau événementiel et coopératif.

TiBillet est un système de paiement sans contact Zéro Espèce ( Cashless ), de gestion d'évènements, de gestion de salles
de restauration, d'engagement associatif et d'achat de billets en ligne … mais pas uniquement !

C'est aussi un outil de mise en réseau et de gestion d'une monnaie locale et commune à plusieurs lieux.

TiBillet permet la création d'une économie sociale et solidaire à l'échelle d'un territoire.

Pour en savoir plus : https://www.tibillet.re & https://wiki.tibillet.re

## Introduction.

TiBillet est en période de BETA et en expérimentation sur plusieurs lieux sur l'ile de la Réunion. Venez nous voir au
Bisik, à la Raffinerie, à Vavang'Art et au Manapany Festival !

Le présent dépot ne contient pas encore toutes les sources du projet. La billetterie est en cours de refactoring et les
sources sont publiées petit à petit sous licence aGPLv3. Mise en production totale prévue fin 2021.

Le Cashless est en cours d'audit de sécurité et sera publié sous licence de type BSL : open-source et libre en dehors de
toute utilisation commerciale type SaaS, avec mise en licence aGPLv3 progressive au fil des financements et des
rentabilisations du développement.

Inspirée par les expériences de Sentry, ElasticSearch, MongoDb, nous souhaitons que TiBillet soit libre d'utilisation
pour toutes structures associatives ou entreprises coopératives à but non lucratif tout en encourageant les acteurs
commerciaux à participer activement au développement.

TiBillet est construit par l'association des 3Peaks de Manapany. Créateurs du Manapany Surf Festival !

## Installation :

We need Docker & docker-compose. See https://docs.docker.com/ for installation.

```shell
cd Docker/Development
# populate .env file with your own variables and copy it.
cp env_example .env
# build docker image
docker-compose build
# launch 
docker-compose up -d
```

## First time launch

```shell

# Go deeper inside the django container :
docker exec -ti tibillet_django bash

# --> Inside the container :
  # apply the db migration ( Django créate the table on postgres )
  python manage.py migrate
  
  # Populate the database with example
  python manage.py createdemo
  
  # Create the root user 
  python manage.py create_tenant_superuser
    -> public
    
  # Launch the http dev' server ( for production, see the Django & gunicorn doc ) 
  python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
  # or you can use the alias from the .bashrc : 
  rsp 
```

Test with ```www.$DOMAIN:8002/admin``` and ```demo.$DOMAIN:8002/admin```
Don't forget to change your /etc/host if you are in localhost :)

```
#example /etc/hosts
127.0.0.1       django-local.org
127.0.0.1       www.django-local.org
127.0.0.1       demo.django-local.org

# go to demo.django-local.org:8002/admin to create an admin user for the tenant. 
```

Enjoy !

## API Documentation 

### API Postman with example :
https://documenter.getpostman.com/view/17519122/UV5agG58

# Crédits :

## Développement :

Jonas TURBEAUX & Nicolas DIJOUX pour 3Peaks2Prod.

TiBillet is ( for the moment ) under the Elastic License 2.0 (ELv2)

Credits:

    Graphical démo :
        Massively by HTML5 UP html5up.net | @ajlkn Free for personal and commercial use under the CCA 3.0 license (
        html5up.net/license)
        AJ aj@lkn.io | @ajlkn
	Demo Images:
		Unsplash (unsplash.com)

	Icons:
		Font Awesome (fontawesome.io)

	Other:
		jQuery (jquery.com)
		Scrollex (github.com/ajlkn/jquery.scrollex)
		Responsive Tools (github.com/ajlkn/responsive-tools)
        Django-jet
        