# TiBillet-Ticket

Réseau événementiel et coopératif.

TiBillet est un système de paiement sans contact Zéro Espèce ( Cashless ), de gestion d'évènements, de gestion de salles
de restauration, d'engagement associatif et d'achat de billets en ligne … mais pas uniquement !

C'est aussi un outil de mise en réseau et de gestion d'une monnaie locale et commune à plusieurs lieux.

TiBillet permet la création d'une économie sociale et solidaire à l'échelle d'un territoire.

Pour en savoir plus : https://www.tibillet.re & https://wiki.tibillet.re

## Design 

![](Presentation/Design_Front_Ticket.svg)

## Introduction.

TiBillet est en période de BETA et en expérimentation sur plusieurs lieux sur l'ile de la Réunion. Venez nous voir au
Bisik, à la Raffinerie, à Vavang'Art et au Manapany Festival !

Le présent dépot ne contient pas encore toutes les sources du projet. La billetterie est en cours de refactoring et les
sources sont publiées petit à petit sous licence libre.

Le Cashless est en cours d'audit de sécurité et sera publié sous licence libre dès que possible.

Pour l'expérimenter chez vous, n'hésitez pas à nous contacter :)

TiBillet est construit par l'association des 3Peaks de Manapany : Créateurs du Manapany Surf Festival !

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
docker exec -ti billetterie_django bash

# --> Inside the container :
  # apply the db migration ( tables creations )
  python manage.py migrate
  
  # Populate the database with example
  # populate DjangoFiles/data/csv/domains_and_cards file with your own variables
  python manage.py create_tenants
  
  # Create the root user 
  python manage.py create_tenant_superuser
    ? -> public
    
  # Launch the http dev' server ( for production, see the Django & gunicorn doc ) 
  python /DjangoFiles/manage.py runserver_plus 0.0.0.0:8002
  # or you can use the alias from the .bashrc : 
  rsp 
  
  # Login in /admin with email/password
```

Test with ```www.$DOMAIN:8002/admin``` and ```demo.$DOMAIN:8002/admin```
Don't forget to change your /etc/host if you are in localhost :)
172.17.0.1 is the docker host network.

```
#example /etc/hosts
172.17.0.1       django-local.org
172.17.0.1       www.django-local.org
172.17.0.1       demo.django-local.org

# go to demo.django-local.org:8002/admin to create an admin user for the tenant. 
```

Enjoy !

# API Documentation 

### API Postman with example :
https://documenter.getpostman.com/view/17519122/UV5agG58

# Licence :

TiBillet is ( for the moment ) under the Server Side Public Licence ( SSPL ), the anti-amazon GPL like licence.

https://www.mongodb.com/licensing/server-side-public-license

https://webassets.mongodb.com/_com_assets/legal/SSPL-compared-to-AGPL.pdf

# Crédits :

## Développement :

#### Lead Dev : Jonas TURBEAUX & Nicolas DIJOUX

Credits:

	D'après une idée originale de l'association des 3Peaks de Manapany et GDNA.
	Merci à :
		Christophe GONTHIER et Flavien BRANCHEREAU
		Tous les bénévoles de l'association des 3Peaks, 
		du Manapany Festival, 
		du Bisik et de la Raffinerie pour avoir essuyé les plâtres !
			
    Landing Page :
        Massively by HTML5 UP html5up.net | @ajlkn Free for personal and commercial use under the CCA 3.0 license (
        html5up.net/license)
        AJ aj@lkn.io | @ajlkn
	Demo Images:
		Unsplash (unsplash.com)

	Icons:
		Font Awesome (fontawesome.io)

	Other:
		Creative-team
		jQuery (jquery.com)
		Scrollex (github.com/ajlkn/jquery.scrollex)
		Responsive Tools (github.com/ajlkn/responsive-tools)
        Django-jet
        Excalidraw
        Bootstrap
        django
		djangorestframework
		requests
		gunicorn
		sentry
		python-dateutil
		Werkzeug
		django-solo
		django-tenants
		djoser
		ipython
		ipdb
		django_debug_toolbar
		django-extensions
		borgbackup
		Pillow
		django-stdimage
		django-weasyprint
		segno
		python-barcode
		celery
		redis
		tenant-schemas-celery        